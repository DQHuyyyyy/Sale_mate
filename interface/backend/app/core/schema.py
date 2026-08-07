"""Kiểm tra database đã chạy tới migration nào.

Migration 001 thêm hai cột số `gia_tri` và `dien_tich_so`. Chưa chạy 001 thì
ứng dụng vẫn tra cứu căn hộ được, chỉ mất bộ lọc khoảng giá — thay vì sập
toàn bộ trang tìm kiếm với lỗi 500.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.db import fetch_one

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def numeric_columns_ready() -> bool:
    """True khi `salemate_v1` đã có cả `gia_tri` lẫn `dien_tich_so`.

    Kết quả được nhớ suốt vòng đời tiến trình — chạy 001 xong phải **khởi động
    lại backend** thì bộ lọc giá mới bật.
    """
    row = fetch_one(
        """
        SELECT count(*) AS so_cot
        FROM information_schema.columns
        WHERE table_name = 'salemate_v1'
          AND column_name IN ('gia_tri', 'dien_tich_so')
        """
    )
    ready = bool(row and row["so_cot"] == 2)
    if not ready:
        logger.warning(
            "salemate_v1 chưa có cột gia_tri/dien_tich_so — bộ lọc khoảng giá tắt. "
            "Chạy interface/backend/migrations/001_alter_salemate_v1.sql "
            "rồi khởi động lại backend."
        )
    return ready
