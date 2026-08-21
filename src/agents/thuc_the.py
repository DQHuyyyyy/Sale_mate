"""Thực thể rút từ câu hỏi, ĐÃ giải tham chiếu bằng lịch sử hội thoại.

Vì sao cần: `build_args` của mọi tool chỉ đọc CÂU HIỆN TẠI. Nên "liệt kê 20 căn
đó" không tool nào nhận — không có tiêu chí nào trong chính câu đó — và khách
nhận "chưa đủ dữ liệu" ngay sau khi trợ lý vừa liệt kê đúng 20 căn ấy. Cùng lý
do mà `suggest.py` phải sinh gợi ý tự chứa đủ tiêu chí, không được dùng từ thay
thế.

Router đọc lịch sử rồi đổ ra đây những DANH TỪ đã giải tham chiếu; tool lấy về
dùng khi câu hiện tại không tự nêu.

## Chỉ chở danh từ, không chở động từ

Đây là ranh giới quan trọng nhất của module này.

- **Danh từ** (mã căn, phân khu, khoảng giá, vốn tự có) — thứ cuộc hội thoại
  đang nói ĐẾN. Kế thừa từ lượt trước là đúng: nói "Ocean Park 1" ở lượt 1 thì
  lượt 2 vẫn đang bàn về Ocean Park 1.
- **Động từ** (muốn vay, muốn đặt cọc, muốn so sánh) — thứ người dùng muốn làm
  NGAY BÂY GIỜ. Kế thừa là sai, và sai theo kiểu nguy hiểm: khách nói "đặt cọc
  VOP397" ở lượt 1, lượt 3 hỏi "căn đó hướng nào" mà kế thừa ý định cọc thì
  `dat_coc` chạy lại và ghi thêm một lead nữa.

Nên `_Y_DINH_VAY`, `_Y_DINH_COC`, `_DAU_HIEU` tổng hợp trong các tool vẫn đọc
đúng câu hiện tại, không bao giờ đọc từ đây.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

_MA_CAN = re.compile(r"\b(V[A-Z]{2}\d{3,4})\b", re.IGNORECASE)

# Khoá được phép. Model trả khoá lạ thì bỏ — cùng tinh thần với `tools/args.py`:
# model là thành phần xác suất, việc của tầng này là làm hậu quả vô hại.
KHOA_SO: tuple[str, ...] = ("gia_min", "gia_max", "dien_tich_min", "dien_tich_max", "von_tu_co")
KHOA_CHU: tuple[str, ...] = ("phan_khu", "loai_can", "huong")
KHOA_DANH_SACH: tuple[str, ...] = ("ma_can",)
KHOA_HOP_LE: frozenset[str] = frozenset(KHOA_SO + KHOA_CHU + KHOA_DANH_SACH)


def lam_sach(tho: Any) -> dict[str, Any]:
    """Lọc output thô của model thành thực thể dùng được.

    Bỏ khoá lạ, bỏ giá trị sai kiểu, bỏ giá trị rỗng. Trả dict rỗng nghĩa là
    "không rút được gì" — và mọi tool phải chạy y như trước khi có module này.
    """
    if not isinstance(tho, dict):
        return {}

    sach: dict[str, Any] = {}
    for khoa, gia_tri in tho.items():
        if khoa not in KHOA_HOP_LE or gia_tri in (None, "", [], {}):
            continue
        da_doc = _doc_mot_khoa(khoa, gia_tri)
        if da_doc is not None:
            sach[khoa] = da_doc
    return sach


def _doc_mot_khoa(khoa: str, gia_tri: Any) -> Any | None:
    if khoa in KHOA_DANH_SACH:
        return _doc_ma_can(gia_tri)
    if khoa in KHOA_SO:
        return _doc_so(gia_tri)
    van_ban = str(gia_tri).strip()
    return van_ban or None


def _doc_ma_can(gia_tri: Any) -> list[str] | None:
    """Chỉ nhận chuỗi khớp ĐÚNG dạng mã căn.

    Không lọc thì model trả "căn góc" hay "20 căn đó" và tool đi tra một mã
    không tồn tại — tệ hơn hẳn so với việc không tra gì.
    """
    tho = gia_tri if isinstance(gia_tri, list) else [gia_tri]
    ma = [m.group(1).upper() for x in tho if (m := _MA_CAN.fullmatch(str(x).strip()))]
    return list(dict.fromkeys(ma)) or None


def _doc_so(gia_tri: Any) -> float | None:
    try:
        so = float(gia_tri)
    except (TypeError, ValueError):
        return None
    return so if so > 0 else None


def ma_can(entities: dict[str, Any] | None) -> list[str]:
    """Mã căn đã giải tham chiếu. Luôn trả list, kể cả khi không có gì."""
    if not entities:
        return []
    gia_tri = entities.get("ma_can") or []
    return list(gia_tri) if isinstance(gia_tri, list) else []


def tieu_chi_tim(entities: dict[str, Any] | None) -> dict[str, Any]:
    """Tiêu chí lọc căn, đổi sang đúng tên tham số của `inventory_search`.

    Cố ý KHÔNG trả mã căn: có mã căn thì việc thuộc về `inventory_lookup` hoặc
    `so_sanh_can`, đúng luật nhường nhau giữa ba tool tồn kho.
    """
    if not entities:
        return {}

    anh_xa = {
        "phan_khu": "subdivision",
        "loai_can": "unit_type",
        "huong": "direction",
        "gia_min": "price_min",
        "gia_max": "price_max",
        "dien_tich_min": "area_min",
        "dien_tich_max": "area_max",
    }
    return {ten_moi: entities[goc] for goc, ten_moi in anh_xa.items() if entities.get(goc)}
