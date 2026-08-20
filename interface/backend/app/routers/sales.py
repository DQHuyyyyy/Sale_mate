from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.columns import (
    COL_DIEN_TICH,
    COL_GIA,
    COL_LOAI_CAN,
    COL_TANG,
    COL_TOA,
)
from app.core.db import fetch_all
from app.core.deps import get_current_user, require_admin
from app.schemas.auth import CurrentUser
from app.schemas.sale import SaleRecord, SaleRecordWithSale

router = APIRouter(prefix="/api/sales", tags=["sales"])

# Cột chung cho hai truy vấn lịch sử bán.
SALE_COLUMNS = f"""
    s.id, s.ma_can, s.sale_id, s.customer_name, s.customer_phone,
    s.sold_price, s.sold_at,
    a.{COL_TOA}       AS toa,
    a.{COL_TANG}      AS tang,
    a.{COL_LOAI_CAN}  AS loai_can,
    a.{COL_DIEN_TICH} AS dien_tich,
    a.{COL_GIA}       AS gia
"""


@router.get("/my-history", response_model=list[SaleRecord])
def my_history(current_user: CurrentUser = Depends(get_current_user)) -> list[SaleRecord]:
    """Lịch sử bán của CHÍNH người đang đăng nhập.

    sale_id lấy từ token. Không có tham số nào cho client đổi được người xem.
    """
    rows = fetch_all(
        f"""
        SELECT {SALE_COLUMNS}
        FROM sales_history s
        LEFT JOIN salemate_v1 a ON a.ma_can = s.ma_can
        WHERE s.sale_id = %s
        ORDER BY s.sold_at DESC
        """,
        (current_user.id,),
    )
    return [SaleRecord(**row) for row in rows]


@router.get("/all", response_model=list[SaleRecordWithSale])
def all_sales(_: CurrentUser = Depends(require_admin)) -> list[SaleRecordWithSale]:
    """Toàn bộ căn đã bán, kèm tên + username của sale (admin)."""
    rows = fetch_all(
        f"""
        SELECT {SALE_COLUMNS},
               u.full_name, u.username
        FROM sales_history s
        LEFT JOIN salemate_v1 a ON a.ma_can = s.ma_can
        LEFT JOIN users u ON u.id = s.sale_id
        ORDER BY s.sold_at DESC
        """
    )
    return [SaleRecordWithSale(**row) for row in rows]

# ⚠️ KHÔNG có route POST ở đây nữa.
#
# Ghi nhận đã bán CHỈ diễn ra ở màn Giao dịch, bằng cách chốt một lead —
# `_chot_ban` trong `routers/dat_coc.py`. Lý do là dữ liệu khách: lead đã giữ
# sẵn tên và số điện thoại người mua, còn form cũ ở trang căn hộ bắt sale gõ
# lại, và gõ sai thì `sales_history` mang tên một người khác với người thật sự
# mua mà không gì đối chiếu được.
#
# Để lại một endpoint bán hàng không còn giao diện nào gọi thì luật "chỉ chốt
# bán trong Giao dịch" chỉ đúng trên màn hình, không đúng trên API.
#
# Cần bán một căn chưa có lead: sale bấm "Đặt cọc căn này" ở trang căn hộ để
# tạo lead trước, rồi chốt ở màn Giao dịch. Hai bước, đổi lại mọi giao dịch đều
# có thông tin liên hệ của người mua.
