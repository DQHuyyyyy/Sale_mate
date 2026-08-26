from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.deps import get_optional_user
from app.core.han_muc import EMAIL_TU_VAN, HanMuc
from app.schemas.auth import CurrentUser
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatError, generate_reply, stream_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Endpoint này công khai nên phải có hạn mức, không thì ai cũng gọi được và mỗi
# lượt đều tốn tiền model. Xem `app/core/han_muc.py` để biết vì sao khách đếm
# theo ngày còn nhân viên đếm theo 10 phút.
KHACH_MOI_NGAY = 15
NHAN_VIEN_MOI_10_PHUT = 120

_han_muc = HanMuc(
    khach_moi_ngay=KHACH_MOI_NGAY,
    nhan_vien_moi_10_phut=NHAN_VIEN_MOI_10_PHUT,
    # Không nói "hết lượt": người hỏi tới câu thứ 16 là người đang thật sự cân
    # nhắc mua. Câu này phải là một lời mời, không phải một cánh cửa đóng lại.
    loi_moi=(
        "Để trao đổi kỹ hơn về căn hộ, bạn liên hệ chuyên viên tư vấn qua email "
        f"{EMAIL_TU_VAN} nhé. Bên mình hỗ trợ trực tiếp, tư vấn theo đúng nhu cầu "
        "và sắp lịch xem căn thực tế."
    ),
)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
) -> ChatResponse:
    """CONTRACT CỐ ĐỊNH: {message, history} -> {reply}.

    Công khai — khách vãng lai hỏi được, chỉ bị giới hạn số lượt. Lõi trả lời
    nằm trong app/services/chat.py; router này không đổi khi thay lõi.
    """
    _han_muc.kiem_tra(request, user)

    try:
        reply = await generate_reply(payload.message, payload.history, payload.session_id)
    except ChatError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ChatResponse(reply=reply)


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
) -> StreamingResponse:
    """Như `/api/chat` nhưng trả SSE — người dùng thấy chữ chạy dần.

    Cùng hạn mức với bản không stream: một lượt hỏi là một lượt, dù đọc kiểu nào.

    Backend chỉ dẫn ống. Lõi AI phát `start` / `route` / `token` / `sources` /
    `done`; event `route` mang `data.step` để widget hiện trợ lý đang làm gì.
    """
    _han_muc.kiem_tra(request, user)

    try:
        stream = stream_reply(payload.message, payload.history, payload.session_id)
        first = await anext(stream)
    except ChatError as exc:
        # Bắt lỗi TRƯỚC khi mở luồng: khi đã trả 200 và bắt đầu stream thì không
        # đổi được status code nữa, client sẽ nhận một luồng rỗng khó hiểu.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    async def body() -> AsyncIterator[bytes]:
        yield first
        async for chunk in stream:
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx/proxy: đừng gom buffer, hỏng streaming
        },
    )
