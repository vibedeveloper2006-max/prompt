"""
models/chat_models.py
---------------------
Schemas for handling AI Assistant API requests.

Security bounds
---------------
- message: max 500 chars — prevents prompt-stuffing and oversized Gemini payloads.
- user_id: max 64 chars — avoids log injection with very long IDs.
- history: max 20 turns — caps context size sent to the model.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The user's query. Maximum 500 characters.",
    )
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Track user context if needed.",
    )
    history: Optional[List[Dict[str, str]]] = Field(
        default_factory=list,
        description="Array of objects e.g., {'role': 'user', 'content': 'hi'}. Max 20 turns.",
        max_length=20,
    )

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: str) -> str:
        """Remove leading/trailing whitespace before length checks fire."""
        return v.strip() if isinstance(v, str) else v


class ChatResponse(BaseModel):
    reply: str
    error: bool = False
