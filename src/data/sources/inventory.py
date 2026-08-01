"""Nạp dữ liệu tồn kho căn hộ thật — CSV (Google Sheet) + ảnh (Google Drive).

Đây là dữ liệu CÓ CẤU TRÚC (giá, diện tích, tình trạng, pháp lý) nên KHÔNG đi
qua pipeline RAG (contracts.py / stores/). Theo Context Product/Kientruc.md
mục 6: "Tồn kho qua tool, không vào vector DB" — module này chỉ chuẩn hoá dữ
liệu thô để cắm vào tool tra cứu tồn kho, không embed, không chunk.

File nguồn nằm ở data/raw/ (bị .gitignore, mỗi máy phải tự tải về — xem
README/hướng dẫn nội bộ), nên mọi hàm ở đây nhận đường dẫn tường minh thay vì
giả định file luôn tồn tại.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel

from src.data.contracts import LoadedDocument

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV_PATH = REPO_ROOT / "data" / "raw" / "inventory.csv"
DEFAULT_PHOTOS_DIR = REPO_ROOT / "data" / "raw" / "photos"

# Sheet hiện chỉ có "Còn"/"Hết"; thêm "giữ chỗ" phòng khi sau này có cột đó.
_STATUS_MAP = {
    "còn": "available",
    "hết": "sold",
    "giữ chỗ": "reserved",
}

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Số cột dữ liệu thật; Excel/Sheet hay export dư cột trắng phía sau.
_DATA_COLUMNS = 13


class InventoryUnit(BaseModel):
    """Một căn hộ trong bảng tồn kho thật — đã chuẩn hoá từ CSV thô."""

    unit_code: str
    building: str
    floor: str
    room_no: str
    unit_type: str
    area_m2: str
    direction: str
    view: str
    legal_status: str
    price_label: str
    furniture: str
    status: str
    photos: list[str] = []


def _normalize_status(raw: str) -> str:
    key = raw.strip().lower()
    return _STATUS_MAP.get(key, key)


def _list_photos(unit_code: str, photos_dir: Path) -> list[str]:
    unit_dir = photos_dir / unit_code
    if not unit_dir.is_dir():
        return []
    return sorted(f.name for f in unit_dir.iterdir() if f.is_file() and f.suffix.lower() in _IMAGE_SUFFIXES)


def load_inventory_csv(
    csv_path: Path = DEFAULT_CSV_PATH,
    photos_dir: Path = DEFAULT_PHOTOS_DIR,
) -> list[InventoryUnit]:
    """Đọc CSV export từ Google Sheet, gắn ảnh theo folder cùng tên mã căn.

    - `utf-8-sig` để tự bỏ BOM (Excel "CSV UTF-8" luôn kèm BOM).
    - Bỏ qua dòng không có mã căn — Sheet/Excel hay export dư hàng trăm dòng
      trống ở cuối vùng dữ liệu.
    - Chỉ đọc 13 cột đầu; cột thừa phía sau (Excel export dư vùng) bị bỏ.
    """
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    units: list[InventoryUnit] = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue

        cells = [cell.strip() for cell in row[:_DATA_COLUMNS]]
        cells += [""] * (_DATA_COLUMNS - len(cells))
        unit_code = cells[0]

        units.append(
            InventoryUnit(
                unit_code=unit_code,
                building=cells[1],
                floor=cells[2],
                room_no=cells[3],
                unit_type=cells[4],
                area_m2=cells[5],
                direction=cells[6],
                view=cells[7],
                legal_status=cells[8],
                price_label=cells[9],
                furniture=cells[10],
                status=_normalize_status(cells[11]),
                photos=_list_photos(unit_code, photos_dir),
            )
        )
    return units


def unit_to_document(unit: InventoryUnit) -> LoadedDocument:
    """Chuyển một căn thành tài liệu mô tả để đưa vào RAG.

    CHỈ đưa nội dung định tính (view, nội thất, hướng, pháp lý) vào text — cố
    tình bỏ giá và tình trạng còn/hết ra khỏi phần embed. Hai trường đó đã có
    tool `inventory_lookup` trả lời chính xác; nhét thêm vào đây sẽ tạo ra hai
    nguồn số liệu có thể lệch nhau theo thời gian (giá cập nhật ở CSV mới
    nhưng vector cũ chưa re-index), đúng thứ nguyên tắc "không bịa số" của dự
    án muốn tránh. Xem Context Product/Kientruc.md mục 6.
    """
    text = (
        f"Căn {unit.unit_code}, toà {unit.building}, tầng {unit.floor}, loại {unit.unit_type}.\n"
        f"Hướng {unit.direction}. {unit.view}.\n"
        f"Pháp lý: {unit.legal_status}.\n"
        f"Nội thất: {unit.furniture}."
    )
    return LoadedDocument(
        doc_id=f"inventory:{unit.unit_code}",
        title=f"Mô tả căn {unit.unit_code} ({unit.building})",
        text=text,
        metadata={
            "visibility": "public",
            "section": unit.building,
            "project": unit.building,
        },
    )


def units_to_documents(units: list[InventoryUnit]) -> list[LoadedDocument]:
    return [unit_to_document(unit) for unit in units]
