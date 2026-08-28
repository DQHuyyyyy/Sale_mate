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
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)


class ChatError(RuntimeError):
    """Gọi lõi AI thất bại — router bắt lại và trả lỗi có nội dung cho người dùng."""


def _loi_tu_status(status_code: int) -> str:
    """Thông điệp theo ĐÚNG loại lỗi, không gộp mọi thứ thành 'đang bận'.

    4xx là request sai — thử lại bao nhiêu lần cũng vậy, nói 'thử lại sau ít
    phút' là đẩy người dùng vào vòng lặp vô ích. 5xx mới là trục trặc tạm thời.
    """
    if status_code == 429:
        return "Trợ lý S đang quá tải. Đợi một chút rồi hỏi lại nhé."
    if 400 <= status_code < 500:
        return "Câu hỏi gửi lên không hợp lệ. Thử mở lại cuộc trò chuyện rồi hỏi lại."
    return "Trợ lý S đang bận. Thử lại sau ít phút."


def _headers() -> dict[str, str]:
    """Khoá dịch vụ gửi kèm mọi lời gọi sang lõi AI.

    Lõi AI có URL công khai trên Render, nên nó chặn request không cầm khoá.
    Rỗng thì không gửi header nào — chỉ chạy được khi lõi AI cũng để rỗng, tức ở
    máy dev. Xem `src/api/bao_ve.py`.
    """
    return {"X-API-Key": settings.ai_core_api_key} if settings.ai_core_api_key else {}


def _build_payload(message: str, history: list[ChatMessage], session_id: str | None = None) -> dict[str, object]:
    """Ghép body theo `ChatRequest` của lõi AI (src/models/chat.py).

    `session_id` chỉ gửi khi client có — bỏ trống thì lõi AI tự sinh và trả về
    trong event `start` để client giữ lại cho lượt sau.
    """
    payload: dict[str, object] = {
        "message": message,
        "history": [{"role": item.role, "content": item.content} for item in history],
    }
    if session_id:
        payload["session_id"] = session_id
    return payload


async def stream_reply(message: str, history: list[ChatMessage], session_id: str | None = None) -> AsyncIterator[bytes]:
    """Dẫn nguyên luồng SSE từ lõi AI về client.

    Backend cố ý KHÔNG parse event: lõi AI đã định dạng SSE đúng chuẩn, và mọi
    loại event mới thêm sau này (tiến trình suy luận, nguồn trích dẫn) tự chảy
    qua mà không phải sửa file này.

    Không dùng `stream_reply` cho client đơn giản — `/api/chat` bản không stream
    vẫn giữ nguyên contract cũ.
    """
    if not settings.chat_enabled:
        raise ChatError("Chatbot chưa được cấu hình. Điền AI_CORE_URL trong .env ở gốc repo rồi khởi động lại backend.")

    url = f"{settings.ai_core_url.rstrip('/')}/api/v1/chat/stream"
    payload = _build_payload(message, history, session_id)

    try:
        async with httpx.AsyncClient(timeout=settings.ai_core_timeout) as client:
            async with client.stream("POST", url, json=payload, headers=_headers()) as response:
                if response.status_code >= 400:
                    body = (await response.aread())[:500]
                    logger.error("Lõi AI trả %s khi stream: %s", response.status_code, body)
                    raise ChatError(_loi_tu_status(response.status_code))

                async for chunk in response.aiter_bytes():
                    yield chunk
    except httpx.HTTPError as exc:
        logger.exception("Không stream được từ lõi AI tại %s", url)
        raise ChatError("Trợ lý S đang không kết nối được. Thử lại sau ít phút.") from exc


async def generate_reply(message: str, history: list[ChatMessage], session_id: str | None = None) -> str:
    if not settings.chat_enabled:
        raise ChatError("Chatbot chưa được cấu hình. Điền AI_CORE_URL trong .env ở gốc repo rồi khởi động lại backend.")

    url = f"{settings.ai_core_url.rstrip('/')}/api/v1/chat"

    try:
        async with httpx.AsyncClient(timeout=settings.ai_core_timeout) as client:
            response = await client.post(url, json=_build_payload(message, history, session_id), headers=_headers())
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được lõi AI tại %s", url)
        raise ChatError(
            "Trợ lý S đang không kết nối được. Kiểm tra lõi AI đã chạy chưa (make run-ai), rồi thử lại."
        ) from exc

    if response.status_code >= 400:
        logger.error("Lõi AI trả %s: %s", response.status_code, response.text[:500])
        raise ChatError(_loi_tu_status(response.status_code))

    try:
        return str(response.json()["message"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Phản hồi của lõi AI sai định dạng")
        raise ChatError("Trợ lý S trả về dữ liệu không đọc được. Thử lại.") from exc
