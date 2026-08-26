"""Schema cho endpoint sinh ảnh."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Ảnh sinh ra thường 1–2MB; base64 phình thêm ~33%. Trần này ứng với ~8MB nhị
# phân, khớp `_TRAN_ANH_BYTE` của service. Đặt ở tầng schema để body quá khổ bị
# chặn trước khi decode, không phải sau.
MAX_ANH_NGUON_CHARS = 12_000_000


class ModifyImageRequest(BaseModel):
    """Yêu cầu sửa một ảnh CỤ THỂ của một căn CỤ THỂ.

    Cố ý không nhận URL ảnh: nhận URL từ client là mở đường cho người lạ bắt
    server tải về bất cứ thứ gì. Server tự tra URL từ `apartment_images` theo
    cặp (ma_can, image_id).

    `anh_nguon` là ngoại lệ CÓ KIỂM SOÁT, để sửa tiếp trên ảnh vừa sinh ra:
    ảnh AI không được lưu ở đâu cả nên lượt sau server không có cách nào tự tìm
    lại nó. Đây KHÔNG phải lỗ hổng SSRF — nó là byte nội tuyến, server không đi
    tải gì cả. Nhưng vẫn phải giữ `ma_can`/`image_id`: chúng buộc mọi yêu cầu
    vào một ảnh có thật của một căn có thật, nên không ai dùng endpoint này làm
    dịch vụ sửa ảnh miễn phí cho ảnh bất kỳ.
    """

    ma_can: str = Field(min_length=1, max_length=32)
    image_id: int = Field(gt=0)
    yeu_cau: str = Field(min_length=3, max_length=500, description="Ví dụ: 'đổi sofa thành màu nâu'")
    anh_nguon: str | None = Field(
        default=None,
        max_length=MAX_ANH_NGUON_CHARS,
        description="Data URI của ảnh AI vừa sinh, để sửa tiếp trên đó. Bỏ trống thì dùng ảnh gốc của căn.",
    )


class ModifyImageResponse(BaseModel):
    """Ảnh trả về dạng data URI, không lưu ở server."""

    anh: str
    la_anh_ai: bool = True
