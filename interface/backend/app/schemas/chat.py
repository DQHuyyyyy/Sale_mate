from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 20


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # min_length khớp với `src/models/chat.py` của lõi AI. Thiếu ràng buộc này
    # thì backend cho lọt tin nhắn rỗng rồi lõi AI mới trả 422 — người dùng nhận
    # một lỗi 502 mơ hồ, còn log lại chỉ ra sai ở tầng trong cùng.
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    """CONTRACT CỐ ĐỊNH — đổi lõi OpenAI sang AI Agent vẫn giữ nguyên hình dạng này."""

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS * 2)
    # Client gửi lại ID mà lõi AI cấp ở lượt đầu. Nhờ vậy log của cả cuộc trò
    # chuyện gom được về một `session_id` thay vì mỗi lượt một ID khác nhau —
    # xem `trace()` trong src/core/logging.py. Bỏ trống thì lõi AI tự sinh.
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    reply: str
