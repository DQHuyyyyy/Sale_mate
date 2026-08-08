from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.deps import get_optional_user
from app.core.ratelimit import RateLimiter
from app.schemas.auth import CurrentUser
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatError, generate_reply

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Endpoint này công khai nên phải có hạn mức, không thì ai cũng gọi được và mỗi
# lượt đều tốn tiền model. Khách chặt tay hơn nhân viên đã đăng nhập.
KHACH_MOI_10_PHUT = 10
NHAN_VIEN_MOI_10_PHUT = 60
CUA_SO_GIAY = 600.0

_gioi_han_khach = RateLimiter(KHACH_MOI_10_PHUT, CUA_SO_GIAY)
_gioi_han_nhan_vien = RateLimiter(NHAN_VIEN_MOI_10_PHUT, CUA_SO_GIAY)


def _kiem_tra_han_muc(request: Request, user: CurrentUser | None) -> None:
    if user is not None:
        con_luot, cho_giay = _gioi_han_nhan_vien.check(f"user:{user.id}")
    else:
        # Sau proxy/CDN thì request.client.host là IP của proxy. Triển khai thật
        # cần đọc X-Forwarded-For và cấu hình proxy tin cậy.
        ip = request.client.host if request.client else "unknown"
        con_luot, cho_giay = _gioi_han_khach.check(f"ip:{ip}")

    if not con_luot:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Bạn đã hỏi khá nhiều trong thời gian ngắn. Thử lại sau {cho_giay} giây, "
                "hoặc đăng nhập để được hỏi nhiều hơn."
            ),
            headers={"Retry-After": str(cho_giay)},
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
    _kiem_tra_han_muc(request, user)

    try:
        reply = await generate_reply(payload.message, payload.history)
    except ChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return ChatResponse(reply=reply)
