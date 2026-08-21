"""Endpoint sinh ảnh — tính năng "Modify Object" trong widget chat.

Vì sao KHÔNG đi qua lõi AI như câu hỏi chat:

* `ChatRequest`/`ChatEvent` là hợp đồng đóng băng, không có chỗ cho `image_id`;
  nhét vào thân câu hỏi kiểu "(căn đang xem: …)" thì đúng loại lỗi đã gây ra ca
  "còn bao nhiêu căn dưới 3 tỷ" trả lời nhầm về một căn.
* Đây là thao tác MỘT BƯỚC, không cần router → retrieve → plan.
* Ảnh là nhị phân, không hợp với đường SSE text.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.deps import get_optional_user
from app.core.ratelimit import RateLimiter
from app.schemas.auth import CurrentUser
from app.schemas.images import ModifyImageRequest, ModifyImageResponse
from app.services.image_edit import ImageEditError, sua_anh_can

router = APIRouter(prefix="/api/images", tags=["images"])

# Chặt hơn hạn mức chat rất nhiều: mỗi lần sinh ảnh tốn gấp nhiều lần một câu
# trả lời văn bản, và endpoint này công khai.
KHACH_MOI_10_PHUT = 5
NHAN_VIEN_MOI_10_PHUT = 20
CUA_SO_GIAY = 600.0

_gioi_han_khach = RateLimiter(KHACH_MOI_10_PHUT, CUA_SO_GIAY)
_gioi_han_nhan_vien = RateLimiter(NHAN_VIEN_MOI_10_PHUT, CUA_SO_GIAY)


def _kiem_tra_han_muc(request: Request, user: CurrentUser | None) -> None:
    if not settings.chat_rate_limit_enabled:
        return

    if user is not None:
        con_luot, cho_giay = _gioi_han_nhan_vien.check(f"user:{user.id}")
    else:
        ip = request.client.host if request.client else "unknown"
        con_luot, cho_giay = _gioi_han_khach.check(f"ip:{ip}")

    if not con_luot:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Bạn đã tạo khá nhiều ảnh trong thời gian ngắn. Thử lại sau {cho_giay} giây, "
                "hoặc đăng nhập để được tạo nhiều hơn."
            ),
            headers={"Retry-After": str(cho_giay)},
        )


@router.post("/modify", response_model=ModifyImageResponse)
async def modify_image(
    payload: ModifyImageRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
) -> ModifyImageResponse:
    """Sửa ảnh của một căn theo yêu cầu bằng lời.

    Trả ảnh dưới dạng data URI, KHÔNG lưu ở đâu cả — đây là ảnh minh hoạ do AI
    tạo cho một tài sản có thật, để lẫn vào ảnh thật là quảng cáo sai sự thật.
    """
    _kiem_tra_han_muc(request, user)

    try:
        anh, mime = await sua_anh_can(payload.ma_can, payload.image_id, payload.yeu_cau)
    except ImageEditError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ModifyImageResponse(anh=f"data:{mime};base64,{base64.b64encode(anh).decode()}")
