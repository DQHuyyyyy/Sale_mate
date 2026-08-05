from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.apartment import PRICE_MAX, PRICE_MIN


class SaleCreate(BaseModel):
    """Ghi nhận một lượt bán.

    KHÔNG có sale_id — backend lấy từ token. Client gửi lên cũng bị bỏ qua.
    """

    ma_can: str = Field(min_length=1, max_length=50)
    customer_name: str | None = Field(default=None, max_length=100)
    customer_phone: str | None = Field(default=None, max_length=20)
    sold_price: Decimal | None = Field(default=None, ge=PRICE_MIN, le=PRICE_MAX)


class SaleRecord(BaseModel):
    id: int
    ma_can: str
    sale_id: int
    customer_name: str | None = None
    customer_phone: str | None = None
    sold_price: Decimal | None = None
    sold_at: datetime | None = None
    # Thông tin căn, join từ salemate_v1 cho tiện hiển thị
    toa: str | None = None
    tang: int | None = None
    loai_can: str | None = None
    dien_tich: str | None = None
    gia: str | None = None


class SaleRecordWithSale(SaleRecord):
    """Bản dành cho admin: kèm tên + username của sale."""

    full_name: str | None = None
    username: str | None = None
