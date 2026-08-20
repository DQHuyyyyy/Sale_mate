from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

# `SaleCreate` đã bị gỡ cùng với route POST /api/sales. Ghi nhận đã bán giờ chỉ
# diễn ra ở màn Giao dịch, và dữ liệu khách lấy thẳng từ lead — không có form
# nào nhận payload bán hàng nữa. Xem chú thích cuối `routers/sales.py`.


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
