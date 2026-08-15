"""Tên cột thật của bảng `salemate_v1` — gom một chỗ duy nhất.

Tên cột trong database KHÔNG khớp `file_md/DATABASE.md`; đây là tên đọc trực
tiếp từ `information_schema` ngày 04/08/2026:

    ma_can · "Tòa" · "Tầng" · "Số phòng" · "Loại căn\\n(PN, WC) Studio"
    "Diện tích" · "Hướng phong thủy" · "View" · "Số đỏ" · "Giá" · "Nội thất"
    "Tình trạng (Còn/Hết)" · "Ảnh"

Ba chỗ dễ sập nhất:
- `"Loại căn\\n(PN, WC) Studio"` có ký tự **xuống dòng** giữa "căn" và "(PN".
- Là `"Số đỏ"`, không phải `"Sổ đỏ"`.
- Là `"Tình trạng (Còn/Hết)"`, không phải `"Tình trạng"`.

Đừng gõ tay tên cột ở nơi khác — import từ đây.
"""

from __future__ import annotations

COL_MA_CAN = "ma_can"
COL_TOA = '"Tòa"'
COL_TANG = '"Tầng"'
COL_SO_PHONG = '"Số phòng"'
COL_LOAI_CAN = '"Loại căn\n(PN, WC) Studio"'
COL_DIEN_TICH = '"Diện tích"'
COL_HUONG = '"Hướng phong thủy"'
COL_VIEW = '"View"'
COL_SO_DO = '"Số đỏ"'
COL_GIA = '"Giá"'
COL_NOI_THAT = '"Nội thất"'
COL_TINH_TRANG = '"Tình trạng (Còn/Hết)"'
# Migration 008. Hiện là dữ liệu DEMO gán theo toà, chưa phải số liệu thật.
COL_PHAN_KHU = '"Phân khu"'

# Cột số do migration 001 thêm. Chưa chạy 001 thì hai cột này chưa tồn tại —
# xem `app/core/schema.py`.
COL_GIA_TRI = "gia_tri"
COL_DIEN_TICH_SO = "dien_tich_so"

# Giá trị trong cột tình trạng. Tên cột ghi "(Còn/Hết)" nên bán xong ghi 'Hết'.
TINH_TRANG_CON = "Còn"
TINH_TRANG_HET = "Hết"


def normalize_sql(expression: str) -> str:
    """Bọc biểu thức để so khớp bỏ qua khoảng trắng và hoa thường.

    Dữ liệu loại căn viết không thống nhất — '1 PN, 1WC', '1PN, 1 WC' và
    '1PN, 1WC' là cùng một loại. So khớp sau khi bỏ hết khoảng trắng.
    """
    return f"replace(lower({expression}), ' ', '')"
