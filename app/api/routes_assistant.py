"""
api/routes_assistant.py
-----------------------
Endpoint for fetching chatbot LLM responses.
Rate-limited to 20 requests per minute per IP to protect upstream Gemini quota.
"""
from fastapi import APIRouter, Depends
from app.middleware.rate_limiter import chat_rate_limit
from app.models.chat_models import ChatRequest, ChatResponse
from app.ai_engine.chatbot import get_chat_response

router = APIRouter(prefix="/assistant", tags=["Assistant"])

@router.post("/chat", response_model=ChatResponse)
def handle_chat(
    request: ChatRequest,
    _rate: None = Depends(chat_rate_limit),
):
    """
    Exposes conversational endpoint mapping to grounded venue rules.
    Bounded to 500-character messages; history capped at 20 turns.
    """
    reply = get_chat_response(request.message, request.history)
    return ChatResponse(reply=reply)
