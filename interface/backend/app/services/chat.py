"""Lõi chatbot — gọi sang lõi AI ở `src/`.

Trước đây hàm này proxy thẳng sang OpenAI. Nay nó gọi service lõi AI
(`src/`, cổng 8001) để câu trả lời đi qua agent graph: router → retrieve
(RAG trên Qdrant) → generate → guardrail. Nhờ vậy trợ lý trả lời dựa trên
tài liệu thật và kèm trích nguồn, thay vì kiến thức chung của model.

Contract `{message, history} -> {reply}` ở router **không đổi**, nên frontend
không phải sửa gì — đúng như thiết kế ban đầu của file này.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)


async def danh_thuc_loi_ai() -> None:
    """Gọi /health của lõi AI cho nó dậy sớm. Không chặn, không ném lỗi.

    Gói free của Render cho service ngủ sau 15 phút không có lưu lượng, và dậy
    lại mất ~1 phút. Hai service ngủ theo hai đồng hồ riêng, nên khách vào web
    chỉ đánh thức service này — lõi AI vẫn ngủ tới câu hỏi đầu tiên, và họ phải
    chờ HAI lần cold start nối tiếp.

    Nuốt mọi lỗi CÓ CHỦ ĐÍCH. Đây là tối ưu trải nghiệm chứ không phải phụ
    thuộc: lõi AI hỏng thì `/api/chat` báo lỗi của chính nó, còn danh sách căn,
    đăng nhập và ảnh không liên quan gì và phải chạy được như thường.

    Timeout 90s chứ không phải `ai_core_timeout`: đang chờ một tiến trình KHỞI
    ĐỘNG, không phải chờ một câu trả lời. Không ai ngồi đợi lời gọi này.

    Thử lại tối đa 3 lượt vì Render trả 429/502 khá thường xuyên ĐÚNG LÚC đang
    dựng container — đã bắt được trong log thật: 429 rồi 502 cách nhau 5 giây,
    và chỉ vài chục giây sau thì service lên bình thường. Thử một lần rồi bỏ
    cuộc nghĩa là chờ trọn một chu kỳ nữa trong khi lõi AI vẫn ngủ.
    """
    url = f"{settings.ai_core_url.rstrip('/')}/health"
    for lan, cho in enumerate((5, 15, 0), start=1):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.get(url)
            if resp.status_code < 400:
                logger.info("Đã đánh thức lõi AI — HTTP %s (lượt %d)", resp.status_code, lan)
                return
            logger.warning("Đánh thức lõi AI trả HTTP %s (lượt %d/3)", resp.status_code, lan)
        except Exception as exc:  # noqa: BLE001 — xem docstring
            logger.warning("Đánh thức lõi AI lỗi %s (lượt %d/3)", exc, lan)
        if cho:
            await asyncio.sleep(cho)
    logger.warning("Không đánh thức được lõi AI sau 3 lượt. Bỏ qua, không ảnh hưởng web.")


async def vong_lap_giu_thuc() -> None:
    """Ping lõi AI đều đặn để nó không bao giờ ngủ. Chạy nền suốt đời tiến trình.

    Vì sao đặt TRONG service này thay vì tạo job thứ hai trên cron ngoài: hai
    service ngủ theo hai đồng hồ riêng, nên giữ thức cần hai nguồn ping. Mà
    service này vốn đã được cron ngoài giữ thức rồi — để nó ping tiếp sang lõi
    AI thì chỉ còn MỘT thứ bên ngoài phải cấu hình đúng, và tắt cả cụm chỉ cần
    đổi `GIU_LOI_AI_THUC` chứ không phải nhớ vào xoá job trên trang web nào đó.

    ⚠️ Vòng lặp này TIÊU GIỜ INSTANCE của gói free Render — 750 giờ mỗi tháng
    cho cả workspace, và giữ thức 24/7 hai service tốn ~48 giờ mỗi ngày. Bật
    quên tắt là Render treo TOÀN BỘ service free tới đầu tháng sau. Đó là lý do
    mặc định TẮT và phải bật tường minh bằng biến môi trường.

    Ngủ TRƯỚC rồi mới ping: `lifespan` đã bắn một phát đánh thức ngay lúc khởi
    động, ping lại ngay lập tức chỉ tổ thừa một lượt.
    """
    logger.info(
        "Giữ lõi AI luôn thức: ping mỗi %d giây. Nhớ TẮT khi hết đợt demo — nó tiêu giờ instance của gói free.",
        settings.chu_ky_giu_thuc_giay,
    )
    while True:
        try:
            await asyncio.sleep(settings.chu_ky_giu_thuc_giay)
            await danh_thuc_loi_ai()
        except asyncio.CancelledError:
            # Tiến trình đang tắt. Phải để CancelledError bay tiếp, nuốt nó là
            # treo luôn quá trình shutdown.
            raise
        except Exception as exc:  # noqa: BLE001
            # Một lượt ping hỏng không được giết vòng lặp: lõi AI có thể đang
            # deploy lại, vài phút nữa là gọi được.
            logger.warning("Vòng giữ thức lỗi (%s), vẫn chạy tiếp.", exc)


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
            async with client.stream("POST", url, json=payload) as response:
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
            response = await client.post(url, json=_build_payload(message, history, session_id))
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
