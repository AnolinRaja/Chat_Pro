from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.config import settings
from app.dependencies import get_current_user, get_current_user_from_token
from app.schemas.audit import AuditAction, AuditActorType, AuditEventType, AuditStatus
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    OrganizationConversationCreate,
    OrganizationConversationResponse,
)
from app.services.audit_service import AuditService
from app.services.connection_manager import connection_manager
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.organization_membership_service import OrganizationMembershipService
from app.services.rate_limiter import auth_rate_limiter

router = APIRouter(tags=["conversations"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/conversations/{conversation_id}")
async def websocket_conversation(websocket: WebSocket, conversation_id: str):
    current_user = None
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        await websocket.close(code=1008)
        return

    try:
        current_user = await get_current_user_from_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return

    try:
        ConversationService.get_conversation(conversation_id, current_user["id"])
    except HTTPException:
        await websocket.close(code=1008)
        return

    admitted = connection_manager.try_add_connection(
        conversation_id,
        websocket,
        current_user["id"],
        settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER,
    )
    if not admitted:
        logger.warning(
            "WebSocket connection rejected due to user limit conversation_id=%s user_id=%s limit=%s",
            conversation_id,
            current_user["id"],
            settings.WEBSOCKET_MAX_CONNECTIONS_PER_USER,
        )
        await websocket.close(code=1008)
        return

    try:
        await websocket.accept()
    except Exception:
        connection_manager.remove_connection(conversation_id, websocket)
        raise
    logger.info(
        "WebSocket connection established for conversation_id=%s user_id=%s",
        conversation_id,
        current_user["id"],
    )

    try:
        while True:
            raw_message = await websocket.receive_text()
            connection_manager.update_activity(websocket)
            message_size = len(raw_message.encode("utf-8"))
            if message_size > settings.WEBSOCKET_MAX_MESSAGE_SIZE_BYTES:
                logger.warning(
                    "WebSocket message rejected due to size limit conversation_id=%s user_id=%s size_bytes=%s limit_bytes=%s",
                    conversation_id,
                    current_user["id"],
                    message_size,
                    settings.WEBSOCKET_MAX_MESSAGE_SIZE_BYTES,
                )
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "WebSocket message is too large."},
                })
                continue

            retry_after = auth_rate_limiter.check(
                f"websocket-message:{current_user['id']}",
                settings.WEBSOCKET_MESSAGE_RATE_LIMIT,
                settings.WEBSOCKET_MESSAGE_RATE_WINDOW_SECONDS,
            )
            if retry_after is not None:
                logger.warning(
                    "WebSocket message rejected due to rate limit conversation_id=%s user_id=%s retry_after_seconds=%s",
                    conversation_id,
                    current_user["id"],
                    retry_after,
                )
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "Too many WebSocket messages. Try again later."},
                })
                continue

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "Invalid JSON payload."},
                })
                continue

            if not isinstance(payload, dict):
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "Payload must be a JSON object."},
                })
                continue

            try:
                validated_message = MessageCreate(**payload)
            except (ValidationError, TypeError, ValueError):
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "Invalid message payload."},
                })
                continue

            try:
                saved_message = MessageService.send_message(conversation_id, current_user["id"], validated_message.content)
            except HTTPException as exc:
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": exc.detail},
                })
                continue
            except Exception:
                logger.exception(
                    "Unexpected message persistence error for conversation_id=%s user_id=%s",
                    conversation_id,
                    current_user["id"],
                )
                await websocket.send_json({
                    "type": "error",
                    "data": {"detail": "Unable to send message."},
                })
                continue

            encoded_message = jsonable_encoder(saved_message)
            await websocket.send_json({"type": "message_ack", "data": encoded_message})
            broadcast_event = {
                "type": "message.created",
                "conversation_id": conversation_id,
                "message": encoded_message,
                # Backward-compatible data field for legacy listeners
                "data": encoded_message,
            }
            participant_user_ids = ConversationService.get_conversation_participant_ids(conversation_id)
            await connection_manager.broadcast(
                conversation_id,
                broadcast_event,
                participant_user_ids=participant_user_ids,
            )
    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected for conversation_id=%s user_id=%s",
            conversation_id,
            current_user["id"] if current_user else None,
        )
    except Exception:
        logger.exception(
            "Unexpected WebSocket error for conversation_id=%s user_id=%s",
            conversation_id,
            current_user["id"] if current_user else None,
        )
    finally:
        connection_manager.remove_connection(conversation_id, websocket)
        logger.info(
            "WebSocket connection removed for conversation_id=%s user_id=%s",
            conversation_id,
            current_user["id"] if current_user else None,
        )


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, current_user: dict = Depends(get_current_user)):
    try:
        result = ConversationService.create_conversation(current_user["id"], payload.other_user_id)
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to create conversation.")


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(current_user: dict = Depends(get_current_user)):
    try:
        return ConversationService.list_conversations(current_user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to retrieve conversations.")


@router.get("/conversations/{conversation_id}")
def get_conversation_by_id(conversation_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return ConversationService.get_conversation(conversation_id, current_user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to retrieve conversation.")


@router.post("/organizations/{organization_id}/conversations", response_model=OrganizationConversationResponse, status_code=status.HTTP_201_CREATED)
def create_organization_conversation(
    request: Request,
    organization_id: str,
    payload: OrganizationConversationCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        from bson import ObjectId
        ObjectId(organization_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format."
        )

    ip_address, user_agent = AuditService.extract_request_context(request)

    if not OrganizationMembershipService.check_membership(current_user["id"], organization_id):
        AuditService.log_event(
            event_type=AuditEventType.ORGANIZATION_CONVERSATION_ACCESS_DENIED,
            actor_type=AuditActorType.USER,
            action=AuditAction.CREATE,
            status=AuditStatus.FAILURE,
            actor_id=current_user["id"],
            actor_role="user",
            organization_id=organization_id,
            target_type="conversation",
            metadata={"reason": "cross_tenant_access_blocked"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: active organization membership required.",
        )

    try:
        conv = ConversationService.create_organization_conversation(
            organization_id=organization_id,
            name=payload.name,
            description=payload.description,
            created_by=current_user["id"],
        )
    except HTTPException:
        raise

    AuditService.log_event(
        event_type=AuditEventType.ORGANIZATION_CONVERSATION_CREATED,
        actor_type=AuditActorType.USER,
        action=AuditAction.CREATE,
        status=AuditStatus.SUCCESS,
        actor_id=current_user["id"],
        actor_role="user",
        organization_id=organization_id,
        target_type="conversation",
        target_id=conv["id"],
        metadata={"name": conv["name"]},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return OrganizationConversationResponse(**conv)


@router.get("/organizations/{organization_id}/conversations", response_model=list[OrganizationConversationResponse])
def list_organization_conversations(
    request: Request,
    organization_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        from bson import ObjectId
        ObjectId(organization_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format."
        )

    if not OrganizationMembershipService.check_membership(current_user["id"], organization_id):
        ip_address, user_agent = AuditService.extract_request_context(request)
        AuditService.log_event(
            event_type=AuditEventType.ORGANIZATION_CONVERSATION_ACCESS_DENIED,
            actor_type=AuditActorType.USER,
            action=AuditAction.READ,
            status=AuditStatus.FAILURE,
            actor_id=current_user["id"],
            actor_role="user",
            organization_id=organization_id,
            target_type="conversation",
            metadata={"reason": "cross_tenant_access_blocked"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: active organization membership required.",
        )

    channels = ConversationService.list_organization_conversations(organization_id)
    return [OrganizationConversationResponse(**c) for c in channels]


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(conversation_id: str, payload: MessageCreate, current_user: dict = Depends(get_current_user)):
    try:
        saved_message = MessageService.send_message(conversation_id, current_user["id"], payload.content)
        encoded_message = jsonable_encoder(saved_message)
        broadcast_event = {
            "type": "message.created",
            "conversation_id": conversation_id,
            "message": encoded_message,
            "data": encoded_message,
        }
        participant_user_ids = ConversationService.get_conversation_participant_ids(conversation_id)
        await connection_manager.broadcast(
            conversation_id,
            broadcast_event,
            participant_user_ids=participant_user_ids,
        )
        return saved_message
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to send message.")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(
    conversation_id: str,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    try:
        messages, next_cursor = MessageService.get_messages_page(
            conversation_id,
            current_user["id"],
            limit,
            cursor,
        )
        if next_cursor is not None:
            response.headers["X-Next-Cursor"] = next_cursor
        return messages
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to retrieve messages.")
