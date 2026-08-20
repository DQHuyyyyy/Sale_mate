from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# Giá lọc trong khoảng 0–20 tỷ VND (quy tắc trong CLAUDE.md).
PRICE_MIN = 0
PRICE_MAX = 20


class ApartmentImage(BaseModel):
    id: int
    image_url: str | None = None
    storage_path: str | None = None
    file_name: str | None = None
    sort_order: int | None = None
    created_at: datetime | None = None


class ApartmentBase(BaseModel):
    """Trả cả cột hiển thị (text) lẫn cột số, đúng như API.md yêu cầu."""

    ma_can: str
    toa: str | None = None
    tang: int | None = None
    so_phong: int | None = None
    loai_can: str | None = None
    dien_tich: str | None = None
    dien_tich_so: Decimal | None = None
    huong: str | None = None
    view: str | None = None
    so_do: str | None = None
    gia: str | None = None
    gia_tri: Decimal | None = None
    noi_that: str | None = None
    # Còn/Hết thô từ `salemate_v1` — vẫn là thứ điều khiển luồng BÁN.
    tinh_trang: str | None = None
    # Ba mức suy ra trong VIEW `inventory_units` (migration 010), dùng để HIỂN
    # THỊ: available · reserved · sold. Có thể None khi chưa chạy 010.
    tinh_trang_chi_tiet: str | None = None
    # Ocean Park 1 / 2 / 3 (migration 008).
    phan_khu: str | None = None


class ApartmentListItem(ApartmentBase):
    thumbnail: str | None = None


class ApartmentDetail(ApartmentBase):
    images: list[ApartmentImage] = []


class ApartmentCreate(BaseModel):
    """Form thêm căn hộ (admin).

    Nhập giá/diện tích bằng SỐ; backend sinh chuỗi hiển thị ("1,8 tỷ", "28m2")
    rồi ghi vào cột text. Cột số `gia_tri`/`dien_tich_so` là GENERATED —
    Postgres tự tính lại từ cột text, backend không ghi vào đó.
    """

    ma_can: str = Field(min_length=1, max_length=50)
    toa: str = Field(min_length=1, max_length=20)
    tang: int | None = Field(default=None, ge=0, le=200)
    so_phong: int | None = None
    loai_can: str | None = Field(default=None, max_length=100)
    dien_tich_so: Decimal = Field(gt=0, le=1000)
    gia_tri: Decimal = Field(ge=PRICE_MIN, le=PRICE_MAX)
    huong: str | None = None
    view: str | None = None
    so_do: str | None = None
    noi_that: str | None = None
    # Giá trị khớp cột "Tình trạng (Còn/Hết)" trong database.
    tinh_trang: str = Field(default="Còn", pattern="^(Còn|Hết)$")
    image_urls: list[str] = []
