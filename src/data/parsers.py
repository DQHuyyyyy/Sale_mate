"""Chuẩn hoá dữ liệu thô từ file crawl.

Dữ liệu gốc là chuỗi do người nhập tay nên rất lộn xộn:

    Giá:        "3,1 tỷ" · "2 tỷ" · "2,120 tỷ" · "800 triệu"
    Diện tích:  "49m2" · "33,5m2" · "27.2m2"      ← lẫn cả dấu , và dấu .
    Loại căn:   "1 PN, 1WC" · "1PN, 1WC" · "Studio"

Không parse được thì tool `price_stats`, `mortgage_calc` và bộ lọc theo ngân
sách đều vô dụng — không ai lọc được `WHERE "3,1 tỷ" < 4000000000`.

Mọi hàm ở đây là hàm thuần: không I/O, không phụ thuộc DB, test bằng assert.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- Giá

_BILLION = 1_000_000_000
_MILLION = 1_000_000

_PRICE_PATTERN = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>tỷ|ty|triệu|trieu|tr)\b",
    re.IGNORECASE,
)


def parse_price_vnd(raw: str | float | int | None) -> int | None:
    """Đổi chuỗi giá tiếng Việt thành số đồng.

    >>> parse_price_vnd("3,1 tỷ")
    3100000000
    >>> parse_price_vnd("2,120 tỷ")
    2120000000
    >>> parse_price_vnd("800 triệu")
    800000000

    Dấu phẩy trong bộ dữ liệu này luôn là dấu thập phân, không phải phân cách
    hàng nghìn — "2,120 tỷ" nghĩa là 2,12 tỷ chứ không phải 2120 tỷ.
    """
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return _price_from_number(float(raw))

    match = _PRICE_PATTERN.search(str(raw))
    if not match:
        return None

    amount = float(match.group("number").replace(",", "."))
    unit = _strip_accents(match.group("unit")).lower()
    multiplier = _BILLION if unit.startswith("ty") else _MILLION
    return int(round(amount * multiplier))


def _price_from_number(value: float) -> int | None:
    """Đoán đơn vị khi ô Excel là số trần, không kèm chữ "tỷ".

    Excel tự đổi vài ô thành số: căn VOP954 có giá ghi là `3.55` chứ không phải
    `"3,55 tỷ"`. Nếu coi số đó là đồng thì căn 3,55 tỷ thành 3 đồng.

    Suy đoán theo bậc độ lớn — an toàn vì ba khoảng cách nhau rất xa:
        < 100        → tỷ      (căn hộ 1–100 tỷ)
        100 … 10⁶    → triệu   (800 → 800 triệu)
        ≥ 10⁶        → đã là đồng
    """
    if value <= 0:
        return None
    if value < 100:
        return int(round(value * _BILLION))
    if value < 1_000_000:
        return int(round(value * _MILLION))
    return int(round(value))


def format_price_label(price_vnd: int | None) -> str:
    """Đổi ngược số đồng thành nhãn hiển thị kiểu Việt Nam."""
    if not price_vnd:
        return ""
    if price_vnd >= _BILLION:
        value = price_vnd / _BILLION
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{text.replace('.', ',')} tỷ"
    value = price_vnd / _MILLION
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} triệu"


# ---------------------------------------------------------------- Diện tích

_AREA_PATTERN = re.compile(r"(?P<number>\d+(?:[.,]\d+)?)\s*(?:m2|m²)?", re.IGNORECASE)


def parse_area_m2(raw: str | float | int | None) -> float | None:
    """Đổi chuỗi diện tích thành số mét vuông.

    >>> parse_area_m2("49m2")
    49.0
    >>> parse_area_m2("33,5m2")
    33.5
    >>> parse_area_m2("27.2m2")
    27.2

    Bộ dữ liệu dùng lẫn cả dấu phẩy và dấu chấm cho phần thập phân nên coi cả
    hai như nhau.
    """
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)

    match = _AREA_PATTERN.search(str(raw).strip())
    if not match:
        return None
    return float(match.group("number").replace(",", "."))


# ---------------------------------------------------------------- Loại căn

_BEDROOM_PATTERN = re.compile(r"(\d+)\s*PN", re.IGNORECASE)
_BATHROOM_PATTERN = re.compile(r"(\d+)\s*WC", re.IGNORECASE)


def parse_layout(raw: str | None) -> tuple[int | None, int | None]:
    """Tách "1 PN, 1WC" thành (số phòng ngủ, số WC).

    >>> parse_layout("2 PN, 2WC")
    (2, 2)
    >>> parse_layout("1PN, 1WC")
    (1, 1)
    >>> parse_layout("Studio")
    (0, 1)

    Chuỗi gốc viết lúc có dấu cách lúc không ("1 PN" vs "1PN") nên nếu không
    chuẩn hoá thì cùng một loại căn bị đếm thành hai loại khác nhau.
    """
    if not raw:
        return None, None

    text = str(raw).strip()
    if "studio" in _strip_accents(text).lower():
        return 0, 1

    bedrooms = _BEDROOM_PATTERN.search(text)
    bathrooms = _BATHROOM_PATTERN.search(text)
    return (
        int(bedrooms.group(1)) if bedrooms else None,
        int(bathrooms.group(1)) if bathrooms else None,
    )


def normalize_layout_label(raw: str | None) -> str:
    """Chuẩn hoá nhãn loại căn để nhóm được: "1PN, 1WC" và "1 PN, 1WC" ra cùng một."""
    bedrooms, bathrooms = parse_layout(raw)
    if bedrooms == 0:
        return "Studio"
    if bedrooms is None:
        return (raw or "").strip()
    if bathrooms is None:
        return f"{bedrooms}PN"
    return f"{bedrooms}PN, {bathrooms}WC"


# ---------------------------------------------------------------- Hướng

_DIRECTIONS = (
    "Đông Bắc",
    "Đông Nam",
    "Tây Bắc",
    "Tây Nam",
    "Đông",
    "Tây",
    "Nam",
    "Bắc",
)


def parse_directions(raw: str | None) -> list[str]:
    """Tách hướng nhà. Một căn có thể có hai hướng: "Đông Bắc - Đông Nam".

    >>> parse_directions("Đông Nam")
    ['Đông Nam']
    >>> parse_directions("Đông Bắc - Đông Nam")
    ['Đông Bắc', 'Đông Nam']

    Trả về danh sách để tool phong thuỷ khớp được cả căn hai hướng.
    """
    if not raw:
        return []

    found: list[str] = []
    for part in re.split(r"[-–/,]", str(raw)):
        cleaned = part.strip()
        if not cleaned:
            continue
        for direction in _DIRECTIONS:
            if _strip_accents(cleaned).lower() == _strip_accents(direction).lower():
                found.append(direction)
                break
    return found


# ---------------------------------------------------------------- Số nguyên


def parse_int(raw: str | float | int | None) -> int | None:
    """Excel trả số nguyên dưới dạng float (27.0). Đưa về int."""
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def clean_text(raw: str | None) -> str:
    """Bỏ khoảng trắng thừa và xuống dòng trong ô Excel."""
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", str(raw)).strip()


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so sánh không phụ thuộc dấu."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")
