from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.columns import (
    COL_DIEN_TICH,
    COL_GIA,
    COL_LOAI_CAN,
    COL_TANG,
    COL_TINH_TRANG,
    COL_TOA,
    TINH_TRANG_CON,
    TINH_TRANG_HET,
)
from app.core.db import fetch_all, get_conn
from app.core.deps import get_current_user, require_admin
from app.core.schema import numeric_columns_ready
from app.schemas.auth import CurrentUser
from app.schemas.sale import SaleCreate, SaleRecord, SaleRecordWithSale

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


@router.post("", response_model=SaleRecord, status_code=status.HTTP_201_CREATED)
def record_sale(
    payload: SaleCreate,
    current_user: CurrentUser = Depends(get_current_user),
) -> SaleRecord:
    """Ghi nhận lượt bán: INSERT sales_history + UPDATE "Tình trạng" = 'Đã bán'.

    Hai thao tác nằm trong một transaction, và căn bị khoá bằng FOR UPDATE nên
    hai sale bấm bán cùng lúc thì chỉ một người thành công.
    """
    # Chưa chạy 001 thì chưa có cột gia_tri để lấy giá niêm yết mặc định.
    gia_tri_select = "gia_tri" if numeric_columns_ready() else "NULL::numeric AS gia_tri"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT ma_can, {COL_TINH_TRANG} AS tinh_trang, {gia_tri_select} "
            "FROM salemate_v1 WHERE ma_can = %s FOR UPDATE",
            (payload.ma_can,),
        )
        apartment = cur.fetchone()

        if apartment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy căn {payload.ma_can}.",
            )
        if apartment["tinh_trang"] != TINH_TRANG_CON:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Căn {payload.ma_can} đã bán rồi. Tải lại danh sách để xem căn còn.",
            )

        sold_price = payload.sold_price if payload.sold_price is not None else apartment["gia_tri"]

        cur.execute(
            """
            INSERT INTO sales_history
                (ma_can, sale_id, customer_name, customer_phone, sold_price)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, ma_can, sale_id, customer_name, customer_phone,
                      sold_price, sold_at
            """,
            (
                payload.ma_can,
                current_user.id,  # LẤY TỪ TOKEN, không nhận từ client
                payload.customer_name,
                payload.customer_phone,
                sold_price,
            ),
        )
        record = cur.fetchone()

        cur.execute(
            f"UPDATE salemate_v1 SET {COL_TINH_TRANG} = %s WHERE ma_can = %s",
            (TINH_TRANG_HET, payload.ma_can),
        )

        cur.execute(
            f"""
            SELECT {COL_TOA} AS toa, {COL_TANG} AS tang,
                   {COL_LOAI_CAN} AS loai_can,
                   {COL_DIEN_TICH} AS dien_tich, {COL_GIA} AS gia
            FROM salemate_v1 WHERE ma_can = %s
            """,
            (payload.ma_can,),
        )
        info = cur.fetchone() or {}

    return SaleRecord(**record, **info)
