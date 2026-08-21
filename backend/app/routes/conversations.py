import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.dependencies import get_current_user, get_current_user_from_token
from app.schemas.conversation import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse
from app.services.conversation_service import ConversationService
from app.services.connection_manager import connection_manager
from app.services.message_service import MessageService

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

    await websocket.accept()
    connection_manager.add_connection(conversation_id, websocket, current_user["id"])
    logger.info(
        "WebSocket connection established for conversation_id=%s user_id=%s",
        conversation_id,
        current_user["id"],
    )

    try:
        while True:
            raw_message = await websocket.receive_text()
            connection_manager.update_activity(websocket)
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
            await connection_manager.broadcast(
                conversation_id,
                {"type": "message", "data": encoded_message},
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


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def send_message(conversation_id: str, payload: MessageCreate, current_user: dict = Depends(get_current_user)):
    try:
        return MessageService.send_message(conversation_id, current_user["id"], payload.content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to send message.")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return MessageService.get_messages(conversation_id, current_user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to retrieve messages.")
