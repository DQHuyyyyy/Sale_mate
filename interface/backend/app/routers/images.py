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

from app.core.deps import get_optional_user
from app.core.han_muc import EMAIL_TU_VAN, HanMuc
from app.schemas.auth import CurrentUser
from app.schemas.images import ModifyImageRequest, ModifyImageResponse
from app.services.image_edit import ImageEditError, sua_anh_can

router = APIRouter(prefix="/api/images", tags=["images"])

# Chặt hơn hạn mức chat: mỗi lần sinh ảnh tốn gấp nhiều lần một câu trả lời văn
# bản (~$0,03 so với ~$0,02), và endpoint này công khai.
KHACH_MOI_NGAY = 10
NHAN_VIEN_MOI_10_PHUT = 40

_han_muc = HanMuc(
    khach_moi_ngay=KHACH_MOI_NGAY,
    nhan_vien_moi_10_phut=NHAN_VIEN_MOI_10_PHUT,
    # Cùng luật với chat: mời liên hệ, không báo hết lượt. Câu khác đi vì người
    # đang thử bố trí nội thất quan tâm thứ khác với người đang hỏi giá.
    loi_moi=(
        "Để xem thêm phương án bố trí nội thất cho căn này, bạn liên hệ chuyên viên "
        f"tư vấn qua email {EMAIL_TU_VAN} nhé. Bên mình dựng phương án chi tiết theo "
        "đúng nhu cầu của bạn."
    ),
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
    _han_muc.kiem_tra(request, user)

    try:
        anh, mime = await sua_anh_can(
            payload.ma_can,
            payload.image_id,
            payload.yeu_cau,
            payload.anh_nguon,
        )
    except ImageEditError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ModifyImageResponse(anh=f"data:{mime};base64,{base64.b64encode(anh).decode()}")
