"""DTO cho luồng chat với trợ lý AI.

ĐÂY LÀ HỢP ĐỒNG GIỮA FE VÀ BE — đổi file này là đổi cả hai bên.
Muốn sửa: mở PR riêng vào develop, cả team review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Một lượt trong hội thoại."""

    role: MessageRole
    content: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChatRequest(BaseModel):
    """Body của POST /api/v1/chat/stream."""

    message: str = Field(
        min_length=1,
        max_length=2000,
        description="Câu hỏi người dùng nhập (khớp bộ đếm x/2000 ở widget)",
    )
    session_id: str | None = Field(
        default=None,
        description="ID phiên hội thoại; bỏ trống thì server tạo mới",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Vài lượt gần nhất để giữ ngữ cảnh",
    )

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Câu hỏi không được để trống")
        return cleaned


class Citation(BaseModel):
    """Nguồn của một khẳng định — nền tảng cho nguyên tắc 'luôn trích nguồn'."""

    doc_id: str
    title: str
    version: str = ""
    page: int | None = None
    section: str = ""
    kind: Literal["doc", "db", "live"] = "doc"


class ChatEventType(StrEnum):
    """Các loại event trong luồng SSE.

    Giai đoạn hiện tại chỉ phát START / TOKEN / DONE / ERROR.
    ROUTE / SOURCES / SENSITIVE đã có sẵn khung để module AI_core bổ sung sau,
    FE không phải đổi hợp đồng khi bật thêm.
    """

    START = "start"
    ROUTE = "route"
    TOKEN = "token"
    SOURCES = "sources"
    SENSITIVE = "sensitive"
    DONE = "done"
    ERROR = "error"


class ChatEvent(BaseModel):
    """Một event SSE gửi về client."""

    type: ChatEventType
    content: str = ""
    session_id: str = ""
    citations: list[Citation] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Serialize sang khung dữ liệu SSE (text/event-stream)."""
        return self.model_dump_json(exclude_defaults=False)


class ChatResponse(BaseModel):
    """Trả lời một lần (không stream) — dùng cho test và client đơn giản."""

    message: str
    session_id: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
