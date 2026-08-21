"""Schema cho endpoint sinh ảnh."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModifyImageRequest(BaseModel):
    """Yêu cầu sửa một ảnh CỤ THỂ của một căn CỤ THỂ.

    Cố ý không nhận URL ảnh: nhận URL từ client là mở đường cho người lạ bắt
    server tải về bất cứ thứ gì. Server tự tra URL từ `apartment_images` theo
    cặp (ma_can, image_id).
    """

    ma_can: str = Field(min_length=1, max_length=32)
    image_id: int = Field(gt=0)
    yeu_cau: str = Field(min_length=3, max_length=500, description="Ví dụ: 'đổi sofa thành màu nâu'")


class ModifyImageResponse(BaseModel):
    """Ảnh trả về dạng data URI, không lưu ở server."""

    anh: str
    la_anh_ai: bool = True
