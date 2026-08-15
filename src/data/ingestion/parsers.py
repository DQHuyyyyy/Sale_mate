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
    """Bỏ khoảng trắng thừa và xuống dòng trong ô Excel.

    CHỈ dùng cho giá trị MỘT DÒNG (ô CSV/Excel: tên toà, tầng, hướng...) —
    gộp cả xuống dòng vì ô Excel không có khái niệm "đoạn văn". Văn bản DÀI
    nhiều dòng (mô tả tin đăng, nội dung tài liệu Markdown) phải dùng
    `sanitize_text()` bên dưới, không dùng hàm này.
    """
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", str(raw)).strip()


# ---------------------------------------------------------------- Làm sạch văn bản dài

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# Số điện thoại VN — có thể có nhãn dẫn ("LH:", "Zalo:"...) hoặc trần.
# Số VN thật đúng 10 chữ số khi bắt đầu bằng 0 ("0" + 9 số nữa) — cố định
# {8,9} (không phải khoảng rộng {9,10}) VÀ chặn biên hai đầu bằng
# (?<!\d)/(?!\d) là bắt buộc, không phải tối ưu thêm — nhưng CHƯA ĐỦ: bug thật
# phát hiện 12/08/2026 — dấu CHẤM là ký tự phân cách của CẢ SĐT (theo thiết kế
# ban đầu) LẪN giá tiền ("10.000.000.000"), nên `(?<!\d)` không chặn được vì
# ký tự ngay trước vị trí khớp giữa là dấu chấm, không phải chữ số. Bỏ hẳn dấu
# chấm khỏi ký tự phân cách cho phép của SĐT — dữ liệu thật ở đây (meeyland/
# batdongsan) không viết SĐT có dấu chấm ngăn nhóm, chỉ giá tiền mới dùng.
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\b(?:LH|Zalo|Call|SĐT|SDT|Hotline|Liên hệ)\b\s*[:\-\s]*)?(?:\+?84|0)(?:[\-\s]?\d){8,9}(?!\d)",
    re.IGNORECASE,
)
_SPAM_PHRASES_PATTERN = re.compile(
    r"\b(?:"
    r"chính chủ cần bán gấp|chính chủ gửi bán|bán gấp|siêu phẩm|"
    r"rẻ nhất thị trường|cam kết rẻ nhất|bao phí sang tên|miễn trung gian|"
    r"miễn quảng cáo|quảng cáo vui lòng không làm phiền|liên hệ em|"
    r"lh em|xem nhà 24\/7|hỗ trợ vay 70%|chiết khấu cực khủng"
    r")\b",
    re.IGNORECASE,
)
_REPEATED_PUNCT_PATTERN = re.compile(r"([.\-*!=?]){3,}")
# Xoá cụm spam/SĐT giữa câu để lại vệt dấu câu rời rạc, vd "đẹp. . , !" —
# gộp một CỤM dấu câu liền nhau (có thể cách nhau bởi khoảng trắng) thành
# đúng 1 dấu, giữ dấu CUỐI cùng trong cụm (thường mang nghĩa rõ nhất).
_PUNCT_CLUSTER_PATTERN = re.compile(r"[.,;:!?](?:\s*[.,;:!?])+")
_HTML_ENTITIES: tuple[tuple[str, str], ...] = (
    ("&nbsp;", " "),
    ("&amp;", "&"),
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&quot;", '"'),
    ("&#39;", "'"),
)
_JUNK_PLACEHOLDERS = frozenset({"nan", "none", "null", "n/a", "undefined", "empty"})


def sanitize_text(raw: str | None) -> str:
    """Làm sạch văn bản DÀI (mô tả tin đăng, nội dung tài liệu...): khử SĐT,
    cụm quảng cáo spam, HTML entity/thẻ còn sót, URL, ký tự unicode ẩn
    (`\\xa0`, `\\u200b`, BOM), dấu câu lặp — KHÔNG đụng vào cấu trúc đoạn.

    Khác `clean_text()`: giữ nguyên xuống dòng đơn/đôi, chỉ gộp khoảng trắng
    NGANG (space/tab) thừa trong từng dòng và gộp 3+ dòng trống liên tiếp
    xuống còn 1 dòng trống.

    Lý do tách riêng — bug thật phát hiện 12/08/2026: một cách làm sạch khác
    (`re.sub(r"\\s+", " ", text)`, gộp CẢ xuống dòng) từng được thử, phá sạch
    heading/bảng/danh sách trong tài liệu kiến thức (`##`, `| Mục | Giá |`,
    gạch đầu dòng) vì gộp hết mọi thứ thành 1 dòng — `ParagraphChunker` dựa
    vào dòng trống (`\\n\\n`) để tách chunk, không còn dòng trống thì cả tài
    liệu thành một "đoạn" bị cắt cứng theo ký tự, không theo cấu trúc.
    """
    if raw is None:
        return ""

    text = raw.strip()
    if text.lower() in _JUNK_PLACEHOLDERS:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ").replace("​", "").replace("﻿", "")

    for entity, replacement in _HTML_ENTITIES:
        text = text.replace(entity, replacement)

    text = _HTML_TAG_PATTERN.sub(" ", text)
    text = _URL_PATTERN.sub("", text)
    text = _PHONE_PATTERN.sub("", text)
    text = _SPAM_PHRASES_PATTERN.sub("", text)
    text = _REPEATED_PUNCT_PATTERN.sub(r"\1", text)
    # Xoá phrase/SĐT ở trên hay để lại vệt dấu câu rời rạc (vd "đẹp. . , !") —
    # gộp lại thành 1 dấu duy nhất trước khi dọn khoảng trắng.
    text = _PUNCT_CLUSTER_PATTERN.sub(lambda m: m.group()[-1], text)

    # Gộp khoảng trắng ngang THEO TỪNG DÒNG — không gộp xuyên dòng, để giữ
    # nguyên ranh giới đoạn/heading/hàng bảng mà bước xoá spam/SĐT ở trên có
    # thể để lại (vd 2 khoảng trắng liền nhau sau khi xoá 1 cụm ở giữa dòng).
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # 3+ dòng trống liên tiếp (phần nội dung bị xoá để lại dòng rỗng) gộp còn 1.
    text = re.sub(r"\n{3,}", "\n\n", text)

    cleaned = text.strip()
    return cleaned if cleaned.lower() not in _JUNK_PLACEHOLDERS else ""


def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so sánh không phụ thuộc dấu."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


# ---------------------------------------------------------------- Loại hình BĐS

# Thứ tự ưu tiên: cụm cụ thể trước, cụm chung ("chung cư") sau — tránh
# "biệt thự liền kề" bị nhận nhầm thành "chung cư" nếu quét cả câu rồi khớp
# nhầm từ khoá chung trước.
_PROPERTY_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("shophouse", "Shophouse"),
    ("biet thu", "Biệt thự"),
    ("lien ke", "Liền kề"),
    ("chung cu", "Chung cư"),
    ("can ho", "Chung cư"),
    ("studio", "Chung cư"),
)


_VIEW_CONTEXT_CHARS = 20


def detect_property_type(text: str) -> str | None:
    """Suy loại hình BĐS (chung cư/biệt thự/liền kề/shophouse) từ từ khoá
    xuất hiện trong văn bản (tiêu đề, mô tả...).

    Chỉ trả kết quả khi có từ khoá rõ ràng — không suy đoán khi mơ hồ, tránh
    gán nhầm loại hình rồi lọc sai khi khách tìm đúng loại.

    Bỏ qua khớp nếu ngay trước từ khoá có chữ "view" (vd "view hồ và biệt
    thự siêu thoáng" — đang tả CẢNH QUAN nhìn thấy từ căn, không phải chính
    căn đó là biệt thự). Phát hiện thật: tin `meeyland:307500673` là căn hộ
    1PN nhưng tiêu đề nhắc "view... biệt thự" khiến bị gắn nhầm — bỏ
    `description` khi gọi hàm không đủ vì cụm này nằm ngay trong tiêu đề.
    """
    if not text:
        return None
    folded = _strip_accents(text).lower()
    for keyword, label in _PROPERTY_TYPE_KEYWORDS:
        for match in re.finditer(re.escape(keyword), folded):
            preceding = folded[max(0, match.start() - _VIEW_CONTEXT_CHARS) : match.start()]
            if "view" in preceding:
                continue
            return label
    return None


# ---------------------------------------------------------------- Mã toà

# Chỉ nhận mã toà khi có từ "tòa/toà" ngay trước — độ chính xác cao hơn quét
# mọi chuỗi giống mã toà trong câu (dễ bắt nhầm tên khu như "The Sapphire 2",
# mã tin rao, số điện thoại...). Cái giá phải trả: bỏ sót tin chỉ nhắc tên khu
# chung mà không ghi mã toà cụ thể — chấp nhận được, "không bịa" quan trọng
# hơn "không bỏ sót".
_BUILDING_CODE_RE = re.compile(r"(?:tòa|toà)\s*([A-Za-z]{1,3}\d{1,3}(?:\.\d{1,2})?)", re.IGNORECASE)


def extract_building_code(text: str) -> str | None:
    """Rút mã toà (vd 'S1.12', 'R105') khi văn bản ghi rõ 'tòa <mã>'."""
    if not text:
        return None
    match = _BUILDING_CODE_RE.search(text)
    return match.group(1).upper() if match else None
