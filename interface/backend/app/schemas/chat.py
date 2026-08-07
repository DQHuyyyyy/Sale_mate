from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 20


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    """CONTRACT CỐ ĐỊNH — đổi lõi OpenAI sang AI Agent vẫn giữ nguyên hình dạng này."""

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS * 2)


class ChatResponse(BaseModel):
    reply: str
