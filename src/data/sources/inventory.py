"""Nạp dữ liệu tồn kho căn hộ thật — CSV (Google Sheet) + ảnh (Google Drive).

Phần định tính (view, nội thất, hướng, pháp lý) ĐƯỢC đưa qua pipeline RAG
(embed + chunk + lưu Qdrant) để trả lời tìm kiếm ngữ nghĩa. Giá và tình trạng
còn/hết KHÔNG đưa vào text embed — hai trường đó chỉ có trong tool
`inventory_lookup` (tra trực tiếp CSV), tránh hai nguồn số liệu lệch nhau
theo thời gian. Xem chi tiết ở `unit_to_document()`.

`visibility = "internal"` — đây là tồn kho THẬT của chính team, chỉ Admin/Sale
được thấy qua RAG (portal công khai không tìm kiếm ra căn hộ nội bộ, chỉ thấy
tin đăng bên thứ 3 từ batdongsan/meeyland). Lọc tại tầng truy hồi qua
`RetrievalFilter.visibility` — không lọc ở UI, đúng nguyên tắc dự án.

File nguồn nằm ở data/raw/ (bị .gitignore, mỗi máy phải tự tải về — xem
README/hướng dẫn nội bộ), nên mọi hàm ở đây nhận đường dẫn tường minh thay vì
giả định file luôn tồn tại.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from src.data.contracts import LoadedDocument
from src.data.ingestion.parsers import sanitize_text

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

# Toàn bộ tồn kho là căn hộ VOP (mã unit_code luôn bắt đầu "VOP") — tức dự án
# Vinhomes Ocean Park Gia Lâm (OCP1). Chuỗi phải khớp CHÍNH XÁC với
# meeyland.PROJECT_OCP1.project_name / batdongsan.DEFAULT_PROJECT /
# knowledge_docs._DEFAULT_PROJECT để RetrievalFilter.project lọc đúng khu.
_PROJECT_NAME = "Vinhomes Ocean Park Gia Lâm"

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
    # view/legal_status/furniture/direction do sale gõ tay vào Sheet — làm
    # sạch (unicode ẩn, dấu câu lặp...) trước khi đưa vào RAG. sanitize_text()
    # giữ nguyên xuống dòng nên không ảnh hưởng cấu trúc heading bên dưới.
    direction = sanitize_text(unit.direction)
    view = sanitize_text(unit.view)
    legal_status = sanitize_text(unit.legal_status)
    furniture = sanitize_text(unit.furniture)

    text = (
        f"# Căn {unit.unit_code} ({unit.building})\n\n"
        f"## Thông tin cơ bản\n"
        f"- Toà: {unit.building}\n"
        f"- Tầng: {unit.floor}\n"
        f"- Loại căn: {unit.unit_type}\n"
        f"- Hướng: {direction}\n\n"
        f"## Tầm nhìn\n{view}\n\n"
        f"## Pháp lý\n{legal_status}\n\n"
        f"## Nội thất\n{furniture}"
    )
    return LoadedDocument(
        doc_id=f"inventory:{unit.unit_code}",
        title=f"Mô tả căn {unit.unit_code} ({unit.building})",
        text=text,
        metadata={
            "visibility": "internal",
            "section": unit.building,
            "project": _PROJECT_NAME,
            "source_site": "noi-bo",
            # Tin rao — tách khỏi tài liệu chính sách để truy hồi lọc được.
            "doc_kind": "listing",
            # Ảnh nằm local (data/raw/photos/), chưa có static server public nên
            # để rỗng thay vì bịa URL — không được hiển thị trên widget cho tới
            # khi có hạ tầng phục vụ ảnh (ngoài phạm vi "data" solo).
            "image_urls": [],
            "local_photo_files": unit.photos,
            "version": datetime.now(UTC).date().isoformat(),
            "doc_kind": "listing",
            # Toà lấy thẳng từ CSV (chính xác tuyệt đối, khác building suy
            # đoán bằng regex ở meeyland/batdongsan). Toàn bộ tồn kho đều là
            # căn hộ chung cư — sự thật đã biết, không phải suy đoán per-record.
            "building": unit.building,
            "property_type": "Chung cư",
        },
    )


def units_to_documents(units: list[InventoryUnit]) -> list[LoadedDocument]:
    return [unit_to_document(unit) for unit in units]
