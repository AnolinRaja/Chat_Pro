from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas.conversation import ConversationCreate, ConversationResponse, MessageCreate, MessageResponse
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService

router = APIRouter(tags=["conversations"])


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
