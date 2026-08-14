"""Endpoint sửa ảnh — đường riêng, KHÔNG đi qua hợp đồng chat.

Vì sao tách khỏi `/chat/stream`: nó trả một tấm ảnh chứ không phải luồng token,
`ChatRequest` không có chỗ cho ảnh, và `src/models/chat.py` thì đóng băng. Ép
vào đó sẽ phải mở PR contract cho cả team review mà chẳng được gì. FE vẫn vẽ kết
quả thành bong bóng trong khung chat — người dùng không thấy khác biệt.

DTO khai ngay tại file này, cũng vì lý do trên: chúng chỉ phục vụ endpoint này.

Endpoint MỞ cho khách chưa đăng nhập theo yêu cầu sản phẩm. Vì mỗi lượt tốn tiền
thật, trần ngày dưới đây là phanh cuối cùng — hạn mức theo IP ở backend không
chặn được chi tiêu tổng vì số IP là vô hạn.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from src.api.deps import SettingsDep
from src.core.container import container
from src.core.exceptions import SalesMateError
from src.core.logging import get_logger, trace
from src.designer.editor import ImageEditService, tai_anh

logger = get_logger(__name__)

# Prefix /api/v1 do main.py gắn khi include — ở đây chỉ khai phần đuôi.
router = APIRouter(prefix="/image", tags=["image"])


MAX_ANH_BYTES = 12 * 1024 * 1024


class ImageEditRequest(BaseModel):
    """Ảnh nguồn đi bằng ĐÚNG MỘT trong hai đường.

    `image_url` cho ảnh gốc của căn hộ. `image_base64` cho lượt sửa TIẾP THEO —
    khi nguồn là ảnh vừa chỉnh xong, chưa hề được lưu ở đâu nên không có URL.
    Nhét nó vào `image_url` không được: data URL của ảnh 1024px dài khoảng 1MB,
    vượt xa giới hạn 2000 ký tự.
    """

    image_url: str = Field(default="", max_length=2000, description="URL công khai của ảnh cần sửa")
    image_base64: str = Field(default="", description="Ảnh nguồn base64 — dùng khi sửa tiếp trên ảnh vừa chỉnh")
    instruction: str = Field(min_length=1, max_length=500, description="Yêu cầu chỉnh sửa, tiếng Việt")
    session_id: str | None = Field(default=None, description="Gom log về một phiên, giống chat")

    @model_validator(mode="after")
    def _dung_mot_nguon(self) -> ImageEditRequest:
        if bool(self.image_url) == bool(self.image_base64):
            raise ValueError("Cần đúng một trong hai: image_url hoặc image_base64.")
        return self


class ImageEditResponse(BaseModel):
    """Một trong hai: `image_base64` có ảnh, hoặc `question` cần hỏi lại."""

    status: str = Field(description="'ok' hoặc 'clarify'")
    image_base64: str = ""
    question: str = ""
    object_edited: str = ""


class _TranNgay:
    """Đếm số ảnh đã sinh trong ngày, tự đặt lại khi sang ngày mới.

    Đếm trong tiến trình: chạy nhiều worker thì mỗi worker có bộ đếm riêng, tức
    trần thực tế nhân với số worker. Chấp nhận được ở quy mô hiện tại; muốn chính
    xác thì chuyển sang Redis, nhưng đừng bỏ hẳn — không có phanh nào còn tệ hơn
    một cái phanh hơi rộng.
    """

    def __init__(self) -> None:
        self._ngay: date = datetime.now(UTC).date()
        self._dem = 0

    def con_luot(self, tran: int) -> bool:
        if tran <= 0:
            return True  # 0 = khong gioi han
        self._xoay_ngay()
        return self._dem < tran

    def ghi_nhan(self) -> None:
        self._xoay_ngay()
        self._dem += 1

    def _xoay_ngay(self) -> None:
        hom_nay = datetime.now(UTC).date()
        if hom_nay != self._ngay:
            self._ngay, self._dem = hom_nay, 0


tran_ngay = _TranNgay()


def _doc_nguon(payload: ImageEditRequest) -> bytes | None:
    """Giải mã ảnh base64, trả None khi request dùng đường URL.

    Chặn kích thước ở đây chứ không tin `Content-Length`: base64 phình 4/3 so với
    bytes thật, và đây là endpoint mở cho khách chưa đăng nhập.
    """
    if not payload.image_base64:
        return None

    try:
        anh = base64.b64decode(payload.image_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ảnh gửi lên không đọc được. Thử đính kèm lại ảnh nhé.",
        ) from exc

    if len(anh) > MAX_ANH_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Ảnh lớn hơn {MAX_ANH_BYTES // (1024 * 1024)}MB. Dùng ảnh nhỏ hơn nhé.",
        )
    return anh


@router.post("/edit", response_model=ImageEditResponse)
async def edit_image(payload: ImageEditRequest, settings: SettingsDep) -> ImageEditResponse:
    """Sửa ảnh theo yêu cầu bằng lời, giữ nguyên phần không được nhắc tới."""
    if not settings.enable_image_edit:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tính năng sửa ảnh đang tắt. Bật ENABLE_IMAGE_EDIT trong .env rồi khởi động lại lõi AI.",
        )

    if not tran_ngay.con_luot(settings.image_daily_limit):
        logger.warning("Chạm trần %s ảnh/ngày", settings.image_daily_limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Tính năng sửa ảnh đã hết lượt hôm nay. Bạn quay lại vào ngày mai nhé.",
            headers={"Retry-After": "3600"},
        )

    with trace(session_id=payload.session_id or "", mode="image_edit"):
        service = container.resolve(ImageEditService)
        try:
            anh_goc = _doc_nguon(payload)
            if anh_goc is None:
                anh_goc = await tai_anh(payload.image_url, toi_da_bytes=MAX_ANH_BYTES)
            ket_qua = await service.sua(anh_goc=anh_goc, lenh=payload.instruction)
        except SalesMateError as exc:
            logger.warning("Sửa ảnh dừng do lỗi nghiệp vụ: %s", exc.code)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc

        if ket_qua.can_hoi_them:
            # Chưa gọi model sinh ảnh nên KHÔNG tính vào trần ngày.
            return ImageEditResponse(status="clarify", question=ket_qua.cau_hoi)

        tran_ngay.ghi_nhan()
        return ImageEditResponse(
            status="ok",
            image_base64=base64.b64encode(ket_qua.anh_png or b"").decode(),
            object_edited=ket_qua.doi_tuong,
        )
