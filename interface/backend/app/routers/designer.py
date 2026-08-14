"""Proxy sang endpoint sửa ảnh của lõi AI, kèm hạn mức RIÊNG.

Vì sao không dùng chung hạn mức với `/api/chat`: một lượt sửa ảnh tốn tiền gấp
khoảng mười lần một lượt chat. Cho chung hạn mức nghĩa là ai cũng đổi được 10
lượt chat rẻ thành 10 lượt ảnh đắt.

Endpoint MỞ cho khách chưa đăng nhập theo yêu cầu sản phẩm. Ba lớp phanh:
hạn mức theo IP ở đây, trần ngày toàn hệ thống ở lõi AI, và cờ ENABLE_IMAGE_EDIT.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.core.deps import get_optional_user
from app.core.ratelimit import RateLimiter
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image", tags=["image"])

# ĐẶT 0 LÀ TẮT HẠN MỨC — đang tắt theo yêu cầu sản phẩm.
#
# Vì sao từng đặt 3: mỗi lượt sửa ảnh tốn gấp khoảng mười lần một lượt chat.
# Nhưng con số đó tính cả lượt trợ lý HỎI LẠI, mà lượt hỏi lại không hề sinh ảnh
# — người dùng bị khoá mười phút sau hai câu hỏi đáp gần như miễn phí.
#
# Bật lại thì nên tách hai tầng (một mức cho mọi request, một mức chặt hơn cho
# lượt thật sự sinh ảnh), đừng quay lại đếm gộp như cũ.
ANH_MOI_10_PHUT = 0
CUA_SO_GIAY = 600.0

_gioi_han = RateLimiter(ANH_MOI_10_PHUT, CUA_SO_GIAY) if ANH_MOI_10_PHUT > 0 else None


class ImageEditRequest(BaseModel):
    """Ảnh nguồn đi bằng đúng một trong hai đường — lõi AI mới là nơi kiểm điều đó.

    `image_base64` phục vụ lượt sửa TIẾP: nguồn khi ấy là ảnh vừa chỉnh xong,
    chưa lưu ở đâu nên không có URL, mà data URL thì dài cả MB.
    """

    image_url: str = Field(default="", max_length=2000)
    image_base64: str = Field(default="")
    instruction: str = Field(min_length=1, max_length=500)
    session_id: str | None = None

    @model_validator(mode="after")
    def _dung_mot_nguon(self) -> "ImageEditRequest":
        """Lặp lại luật của lõi AI, có chủ ý.

        Backend vốn chỉ dẫn ống, nhưng chặn ở đây tiết kiệm nguyên một vòng gọi
        mạng cho một request chắc chắn sai. Lõi AI vẫn kiểm lại — nó là nơi thực
        thi, đây chỉ là cửa lọc sớm.
        """
        if bool(self.image_url) == bool(self.image_base64):
            raise ValueError("Cần đúng một trong hai: image_url hoặc image_base64.")
        return self


class ImageEditResponse(BaseModel):
    status: str
    image_base64: str = ""
    question: str = ""
    object_edited: str = ""


@router.post("/edit", response_model=ImageEditResponse)
async def edit_image(
    payload: ImageEditRequest,
    request: Request,
    user: CurrentUser | None = Depends(get_optional_user),
) -> ImageEditResponse:
    """Sửa ảnh căn hộ theo yêu cầu bằng lời.

    Backend không xử lý ảnh — toàn bộ việc đó nằm ở lõi AI. Ở đây chỉ chặn lưu
    lượng và chuyển tiếp.
    """
    if not settings.chat_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chưa cấu hình AI_CORE_URL nên chưa sửa được ảnh.",
        )

    if _gioi_han is not None:
        khoa = f"user:{user.id}" if user else f"ip:{request.client.host if request.client else 'unknown'}"
        con_luot, cho_giay = _gioi_han.check(khoa)
        if not con_luot:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Bạn vừa sửa khá nhiều ảnh. Thử lại sau {cho_giay} giây nhé.",
                headers={"Retry-After": str(cho_giay)},
            )

    url = f"{settings.ai_core_url.rstrip('/')}/api/v1/image/edit"
    try:
        # Timeout dài hơn chat: sinh ảnh lâu hơn hẳn sinh chữ.
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload.model_dump())
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được lõi AI để sửa ảnh tại %s", url)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Trợ lý S đang không kết nối được. Thử lại sau ít phút.",
        ) from exc

    if response.status_code >= 400:
        # Chuyển nguyên thông điệp của lõi AI: nó nói rõ hết lượt ngày hay tính
        # năng đang tắt, gộp thành một câu chung là nuốt mất thông tin hữu ích.
        detail = _doc_loi(response)
        logger.warning("Lõi AI trả %s khi sửa ảnh: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail=detail)

    return ImageEditResponse(**response.json())


def _doc_loi(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "Trợ lý S chưa sửa được ảnh này. Thử lại sau ít phút."
    return detail if isinstance(detail, str) else "Trợ lý S chưa sửa được ảnh này."
