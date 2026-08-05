"""Lõi chatbot — hiện là proxy sang OpenAI.

Giai đoạn 7 sẽ thay hàm `generate_reply` bằng AI Agent Python. Chỉ hàm này đổi;
contract `{message, history} -> {reply}` ở router giữ nguyên nên frontend không
phải sửa gì.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Bạn là 'Trợ lý S' của SalesMate — trợ lý cho nhân viên sale bán căn hộ trong "
    "một khu đô thị.\n"
    "Quy tắc:\n"
    "1. KHÔNG bịa số. Giá, diện tích, tình trạng căn chỉ nêu khi người dùng đã "
    "cung cấp trong hội thoại. Nếu chưa có, hướng dẫn họ dùng bộ lọc 'Tìm kiếm "
    "căn hộ' trên trang chủ để lấy dữ liệu thật.\n"
    "2. Nếu không chắc, nói thẳng là chưa có dữ liệu — đừng suy đoán.\n"
    "3. Trả lời bằng tiếng Việt, ngắn gọn, câu chủ động, giọng đồng nghiệp.\n"
    "4. Được phép tư vấn kỹ năng bán hàng, cách xử lý câu hỏi của khách, so sánh "
    "hướng nhà/view theo hiểu biết chung."
)


class ChatError(RuntimeError):
    """Gọi model thất bại — router bắt lại và trả lỗi có nội dung cho người dùng."""


def _build_messages(message: str, history: list[ChatMessage]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend({"role": item.role, "content": item.content} for item in history)
    messages.append({"role": "user", "content": message})
    return messages


async def generate_reply(message: str, history: list[ChatMessage]) -> str:
    if not settings.chat_enabled:
        raise ChatError(
            "Chatbot chưa được cấu hình. Điền OPENAI_API_KEY trong backend/.env "
            "rồi khởi động lại backend."
        )

    payload = {
        "model": settings.openai_model,
        "messages": _build_messages(message, history),
        "temperature": 0.3,
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được OpenAI")
        raise ChatError("Trợ lý S đang không kết nối được. Thử lại sau ít phút.") from exc

    if response.status_code >= 400:
        logger.error("OpenAI trả %s: %s", response.status_code, response.text[:500])
        raise ChatError("Trợ lý S đang bận. Thử lại sau ít phút.")

    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        logger.exception("Phản hồi OpenAI sai định dạng")
        raise ChatError("Trợ lý S trả về dữ liệu không đọc được. Thử lại.") from exc
