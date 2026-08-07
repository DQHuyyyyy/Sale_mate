"""Lõi chatbot — gọi sang lõi AI ở `src/`.

Trước đây hàm này proxy thẳng sang OpenAI. Nay nó gọi service lõi AI
(`src/`, cổng 8001) để câu trả lời đi qua agent graph: router → retrieve
(RAG trên Qdrant) → generate → guardrail. Nhờ vậy trợ lý trả lời dựa trên
tài liệu thật và kèm trích nguồn, thay vì kiến thức chung của model.

Contract `{message, history} -> {reply}` ở router **không đổi**, nên frontend
không phải sửa gì — đúng như thiết kế ban đầu của file này.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)


class ChatError(RuntimeError):
    """Gọi lõi AI thất bại — router bắt lại và trả lỗi có nội dung cho người dùng."""


def _build_payload(message: str, history: list[ChatMessage]) -> dict[str, object]:
    """Ghép body theo `ChatRequest` của lõi AI (src/models/chat.py).

    Hai contract gần như trùng nhau; lõi AI có thêm `session_id` tuỳ chọn nên
    bỏ trống để nó tự sinh.
    """
    return {
        "message": message,
        "history": [{"role": item.role, "content": item.content} for item in history],
    }


async def generate_reply(message: str, history: list[ChatMessage]) -> str:
    if not settings.chat_enabled:
        raise ChatError("Chatbot chưa được cấu hình. Điền AI_CORE_URL trong backend/.env rồi khởi động lại backend.")

    url = f"{settings.ai_core_url.rstrip('/')}/api/v1/chat"

    try:
        async with httpx.AsyncClient(timeout=settings.ai_core_timeout) as client:
            response = await client.post(url, json=_build_payload(message, history))
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được lõi AI tại %s", url)
        raise ChatError(
            "Trợ lý S đang không kết nối được. Kiểm tra lõi AI đã chạy chưa (make run-ai), rồi thử lại."
        ) from exc

    if response.status_code >= 400:
        logger.error("Lõi AI trả %s: %s", response.status_code, response.text[:500])
        raise ChatError("Trợ lý S đang bận. Thử lại sau ít phút.")

    try:
        return str(response.json()["message"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Phản hồi của lõi AI sai định dạng")
        raise ChatError("Trợ lý S trả về dữ liệu không đọc được. Thử lại.") from exc
