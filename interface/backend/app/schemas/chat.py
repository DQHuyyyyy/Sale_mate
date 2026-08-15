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
    #
    # CỐ Ý KHÔNG có max_length, và đây là chỗ khác `message` bên dưới. Lõi AI
    # cũng chỉ đặt max_length cho `message`, không đặt cho content của history:
    # 2000 ký tự là trần của thứ NGƯỜI DÙNG gõ (khớp bộ đếm x/2000 ở widget),
    # còn history chứa cả câu trả lời do MODEL sinh, dài bao nhiêu không ai
    # kiểm soát được. Đừng "cho đồng bộ" rồi thêm max_length vào đây.
    content: str = Field(min_length=1)


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
