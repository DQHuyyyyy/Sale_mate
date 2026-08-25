"""Tool tìm căn theo tiêu chí — bổ sung cho `inventory_lookup` tra theo mã căn.

Hai tool loại trừ nhau tự nhiên: `inventory_lookup` cần mã căn, tool này cần
tiêu chí. Câu có mã căn thì tool này im lặng, để tool kia trả lời chính xác một
căn thay vì trả về một danh sách.

KHÔNG hardcode danh sách toà nhà hay loại căn. Từ vựng lọc đọc từ chính SQL:
thêm toà mới vào dữ liệu là tool nhận ra ngay, không ai phải sửa code. Đây cũng
là cách duy nhất không bỏ sót khi dữ liệu ghi không thống nhất — trước đây cột
loại căn có 10 cách viết cho 6 loại, hardcode '%2PN%' sẽ mất sạch những căn ghi
'2 PN'. Chuẩn hoá cả hai vế trước khi so là xong.

Phần duy nhất là luật ngôn ngữ, không phải dữ liệu: "phòng ngủ" -> "PN" và
"view X" -> tìm X trong cột View. Ánh xạ tiếng Việt sang tên cột thì không
tránh được, nhưng giữ ở mức tối thiểu.
"""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.thuc_the import ma_can as ma_can_tu_thuc_the
from src.agents.thuc_the import tieu_chi_tim
from src.agents.tools import trang_thai as tt
from src.agents.tools.args import doc_tham_so
from src.agents.tools.registry import register_tool
from src.core.logging import get_logger
from src.data.stores.inventory_db import get_inventory_db

logger = get_logger(__name__)

# Trần số căn đưa vào prompt.
#
# Từng để 8, và "liệt kê các căn dưới 3 tỷ" thành không thể trả lời đúng: kho có
# 21 căn khớp mà model chỉ nhận được 8. Không phải agent hiểu sai — nó không
# được cấp đủ dữ liệu.
#
# Nâng được lên 30 nhờ `_gon` cắt bớt trường: mỗi căn còn 9 trường thay vì 15,
# nên 30 căn gọn hơn 8 căn bản đầy đủ trước đây.
MAX_RESULTS = 30

# Trường thật sự cần để tư vấn. Bỏ `floor`/`room_no` (không ai hỏi tầng mấy khi
# đang duyệt danh sách), `photos` (mảng đường dẫn, model không dùng được),
# `price_value`/`area_value` (bản số của `price_label`/`area_m2`, lặp), và
# `status` (tool đã lọc chỉ còn căn available).
_TRUONG_GON = (
    "unit_code",
    "subdivision",
    "building",
    "unit_type",
    "area_m2",
    "direction",
    "view",
    "price_label",
    "legal_status",
    "furniture",
)


def _gon(row: dict[str, Any]) -> dict[str, Any]:
    """Bản rút gọn của một căn, để chở được nhiều căn trong cùng ngân sách token.

    Kèm `status_label` vì kết quả tìm kiếm giờ có cả căn đang giữ chỗ / đã đặt
    cọc. Thiếu nhãn thì model đọc danh sách và chào tất cả như nhau — khách gọi
    hỏi mua một căn đã có người đặt.
    """
    gon = {k: row[k] for k in _TRUONG_GON if k in row}
    gon["status_label"] = tt.nhan(row.get("status"))
    return gon


# Từ vựng đọc từ SQL nên phải làm mới, nhưng không phải mỗi lượt hỏi.
_VOCAB_TTL_S = 300.0

_UNIT_CODE = re.compile(r"\b[A-Za-z]{2,4}\d{2,5}\b")

# Đuôi ngữ cảnh do WIDGET chèn, không phải lời người dùng. Xem `themNguCanh`
# trong interface/frontend/src/components/ChatSidebar.jsx — đang mở một căn mà
# hỏi trống không ("phân tích căn này") thì FE gắn mã căn vào để tool tra được.
#
# Nhưng nó gắn cho MỌI câu không chứa mã căn, kể cả câu có tiêu chí riêng. Ca
# thật: bấm trích nguồn "VOP237" xong hỏi "còn bao nhiêu căn dưới 3 tỷ" thì câu
# gửi đi thành "... (căn đang xem: VOP237)". Luật "có mã căn thì nhường
# inventory_lookup" khớp phải mã do FE chèn, `inventory_search` im, và trợ lý
# trả lời "chỉ có thông tin về căn VOP237".
#
# `inventory_lookup` VẪN đọc cả câu — nó cần mã đó. Chỉ tool tìm kiếm mới phải
# bỏ qua, vì nó quyết định dựa trên việc người dùng CÓ tự nêu mã căn hay không.
_NGU_CANH_GIAO_DIEN = re.compile(r"\s*\(căn đang xem:[^)]*\)\s*", re.IGNORECASE)


def bo_ngu_canh_giao_dien(query: str) -> str:
    """Bỏ đuôi widget chèn, để lại đúng lời người dùng gõ.

    MỌI tool quyết định dựa trên "người dùng CÓ tự nêu mã căn không" đều phải
    gọi hàm này trước. `inventory_summary` từng quên: nó bỏ chạy khi thấy mã căn,
    mà mã đó do FE chèn — nên "Ocean Park 3 còn bao nhiêu căn đang bán?" hỏi lúc
    đang mở VOP758 thì tool đếm im lặng, và trợ lý trả lời "chưa đủ dữ liệu…
    căn đang xem là VOP758 thuộc Ocean Park 1".
    """
    return _NGU_CANH_GIAO_DIEN.sub("", query)


# Câu hỏi ĐẾM — hỏi một con số tổng hợp, không hỏi danh sách căn.
#
# Tách riêng khỏi `_DAU_HIEU` rộng hơn của `inventory_summary`: danh sách này
# quyết định `inventory_search` có NHƯỜNG hay không, nên phải hẹp. "cho tôi xem
# các căn đã bán" cũng là câu tổng hợp với summary, nhưng người dùng muốn một
# DANH SÁCH — nhường ở đó là trả nhầm một con số.
_DAU_HIEU_DEM = (
    "bao nhiêu căn",
    "còn bao nhiêu",
    "số lượng căn",
    "mấy căn",
    "tổng số căn",
    "còn mấy",
    "đếm số",
    "thống kê",
)


def la_cau_hoi_dem(query: str) -> bool:
    """Câu hỏi xin một CON SỐ tổng hợp chứ không xin danh sách căn."""
    thap = bo_ngu_canh_giao_dien(query).lower()
    return any(dau in thap for dau in _DAU_HIEU_DEM)


# Tiêu chí mà `inventory_summary` lọc được — đúng các trường của `SummaryArgs`.
# Nó KHÔNG biết giá, diện tích, hướng hay view.
_SUMMARY_LO_DUOC = frozenset({"subdivision", "building", "unit_type"})


# "2 phòng ngủ", "2pn", "2 PN" — số phòng ngủ là tiêu chí hay được hỏi nhất.
_BEDROOMS = re.compile(r"(\d)\s*(?:phòng\s*ngủ|pn\b)", re.IGNORECASE)
# "1 vệ sinh", "2WC", "2 nhà vệ sinh", "1 toilet".
#
# Phải xét ĐỘC LẬP với số phòng ngủ. Trước đây chỉ đọc phòng ngủ nên "2 phòng
# ngủ và 1 vệ sinh ở Ocean Park 3" cho ra 15 căn — gồm cả 9 căn 2PN-2WC — trong
# khi đáp án đúng là 6. Trợ lý nói sai số, không phải chỉ hiện thừa.
_WC = re.compile(r"(\d)\s*(?:nhà\s*)?(?:vệ\s*sinh|ve\s*sinh|wc\b|toilet)", re.IGNORECASE)
# Phân khu: "Ocean Park 2", "OceanPark 2", "OP2", "phân khu 2", "khu 3".
# Chỉ nhận số 1-3 — dự án có đúng ba phân khu, bắt "khu 7" rồi lọc ra rỗng thì
# người dùng không hiểu vì sao.
_PHAN_KHU = re.compile(
    r"(?:ocean\s*park|op|phân\s*khu|phan\s*khu|khu)\s*([123])\b",
    re.IGNORECASE,
)
# "view biển", "view hồ" — lấy ĐÚNG MỘT từ ngay sau chữ "view".
# Lấy hai từ thì "view hồ tòa R103" thành từ khoá "hồ tòa" và không khớp gì cả.
# Một từ có thể rộng hơn ý người hỏi, nhưng rộng còn trả về căn thật; sai thì
# trả rỗng và người dùng không hiểu vì sao.
_VIEW = re.compile(r"view\s+([^\s,.]+)", re.IGNORECASE)


def _fold(text: str) -> str:
    """Bỏ dấu tiếng Việt, bỏ mọi khoảng trắng và dấu câu, viết hoa.

    Nhờ vậy '2 PN, 1WC' và '2PN,1WC' và '2pn 1wc' đều thành '2PN1WC'.
    """
    no_mark = unicodedata.normalize("NFD", text)
    no_mark = "".join(ch for ch in no_mark if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^0-9A-Za-z]", "", no_mark).upper()


class _Vocabulary:
    """Giá trị hợp lệ của từng cột, đọc từ SQL và nhớ tạm theo TTL."""

    def __init__(self) -> None:
        self._values: dict[str, list[str]] = {}
        self._loaded_at = 0.0

    def get(self) -> dict[str, list[str]]:
        if not self._values or time.monotonic() - self._loaded_at > _VOCAB_TTL_S:
            self._reload()
        return self._values

    def _reload(self) -> None:
        rows = get_inventory_db().query_units()
        self._values = {
            field: sorted({str(r[field]) for r in rows if r.get(field)})
            for field in ("unit_type", "building", "direction")
        }
        self._loaded_at = time.monotonic()
        logger.info(
            "Nạp từ vựng lọc từ SQL: %s",
            {k: len(v) for k, v in self._values.items()},
        )

    def clear(self) -> None:
        self._values = {}
        self._loaded_at = 0.0


vocabulary = _Vocabulary()


def _match_unit_type(query: str, values: list[str]) -> str | None:
    """Khớp loại căn: ưu tiên số phòng ngủ, sau đó tên gọi thẳng (Studio)."""
    match = _BEDROOMS.search(query)
    if match:
        wanted = f"{match.group(1)}PN"
        # Trả giá trị THẬT trong DB, không trả chuỗi tự chế.
        hits = [v for v in values if _fold(v).startswith(wanted)]
        return hits[0] if len(hits) == 1 else (wanted if hits else None)

    folded = _fold(query)
    for value in values:
        if _fold(value) in folded:
            return value
    return None


def _match_building(query: str, values: list[str]) -> str | None:
    """Khớp toà nhà theo TỪ RIÊNG, không phải chuỗi con.

    Có mã toà chỉ hai ký tự ('S1', 'H2', 'P3'), khớp chuỗi con sẽ bắt nhầm khi
    chúng nằm lọt giữa một từ khác. So theo token thì 'S210' trong câu chỉ khớp
    toà S210, không khớp S2.
    """
    tokens = {_fold(t) for t in re.split(r"[^0-9A-Za-zÀ-ỹ]+", query) if t}
    by_value = {_fold(v): v for v in values}
    for token in sorted(tokens, key=len, reverse=True):
        if token in by_value:
            return by_value[token]
    return None


def _match_direction(query: str, values: list[str]) -> str | None:
    """Khớp hướng — giá trị nhiều từ nên phải so chuỗi con, không so token.

    Xét giá trị dài trước: 'Đông Bắc - Đông Nam' cụ thể hơn 'Đông Nam'.
    """
    folded = _fold(query)
    for value in sorted(values, key=len, reverse=True):
        if _fold(value) and _fold(value) in folded:
            return value
    return None


# Đơn vị DIỆN TÍCH. Phải khai ở đây vì số tiền cũng nhận đơn vị tuỳ chọn, nên
# không loại trừ thì "43m²" bị đọc thành 43 TỶ.
_DON_VI_DIEN_TICH = r"m\s*(?:²|2\b)|met\s*vuong|mét\s*vuông|mét\s*vuong"

# Số tiền: một con số kèm đơn vị TUỲ CHỌN. Người dùng viết đủ kiểu —
# "3 tỷ", "2,5 tỷ", "500 triệu", "5.000.000.000", "5000000000".
#
# Hai lookahead sau con số, cả hai đều cần thiết:
#
# - `(?![\d.,])` chặn regex lùi lại khớp một phần con số. Không có nó thì ở
#   "43m²" máy thử "43" → hỏng vì lookahead diện tích → lùi về "4" → "4" đứng
#   trước "3" nên lookahead diện tích qua được, và "4 tỷ" lọt vào tiêu chí.
# - lookahead diện tích chặn chính ca đã xảy ra thật: bấm gợi ý "Tìm căn khoảng
#   43m² ở Ocean Park 1" thì `khoảng 43` khớp _QUANH, ra `price 42,8 – 43,2`
#   TỶ. Kho không có căn nào giá 43 tỷ nên trả rỗng, trợ lý nói "chưa đủ dữ
#   liệu", rồi lượt gợi ý sau lại dựng "giá 42,8–43,2" từ chính tiêu chí sai đó
#   — người dùng bấm hai lần liên tiếp vào hai ngõ cụt.
_SO = rf"(\d[\d.,]*)(?![\d.,])(?!\s*(?:{_DON_VI_DIEN_TICH}))"
_DON_VI = r"\s*(tỷ|ty|triệu|trieu|tr|đồng|dong|vnd|vnđ)?"
_TIEN = rf"{_SO}{_DON_VI}"

# Diện tích: cùng cách nói với giá nhưng đơn vị BẮT BUỘC, nếu không thì "khoảng
# 43" ở câu về giá lại thành diện tích.
_DT = rf"(\d[\d.,]*)\s*(?:{_DON_VI_DIEN_TICH})"

_KHOANG = re.compile(rf"(?:từ\s*)?{_TIEN}\s*(?:-|–|—|đến|tới)\s*{_TIEN}", re.IGNORECASE)

# Tách "dưới/trên" (NGHIÊM NGẶT) khỏi "không quá/tối đa" (bao gồm biên) — tiếng
# Việt phân biệt rõ hai nhóm này và người dùng đếm được sự khác nhau. Kho hiện
# có 4 căn giá đúng 3 tỷ: "dưới 3 tỷ" ra 21 căn, "không quá 3 tỷ" ra 25.
_DUOI_NGHIEM = re.compile(rf"(?:dưới|nhỏ hơn|ít hơn|thấp hơn|<)\s*{_TIEN}", re.IGNORECASE)
_DUOI_BAO_GOM = re.compile(rf"(?:không quá|tối đa|không vượt quá|<=)\s*{_TIEN}", re.IGNORECASE)
_TREN_NGHIEM = re.compile(rf"(?:trên|lớn hơn|cao hơn|hơn|>)\s*{_TIEN}", re.IGNORECASE)
_TREN_BAO_GOM = re.compile(rf"(?:từ|tối thiểu|ít nhất|>=)\s*{_TIEN}", re.IGNORECASE)

# "khoảng 3 tỷ", "tầm giá 3 tỷ" — người mua nói một mốc nhưng ý là quanh mốc đó.
# Lọc đúng bằng mốc thì hầu như không căn nào khớp, mà nới vô hạn thì mất nghĩa.
#
# Giữa từ chỉ mức và con số hay có một từ đệm: "khoảng GIÁ 3 tỷ", "tầm MỨC GIÁ
# 3 tỷ". Bản đầu chỉ phủ "tầm giá" nên "khoảng giá 3 tỷ" rơi ra ngoài, không rút
# được tiêu chí nào, tool tìm kiếm im — và trước khi dọn Qdrant thì câu hỏi rơi
# xuống tin rao của sàn khác. Nới từ đệm thành tuỳ chọn dùng chung cho mọi từ.
_TU_CHI_MUC = r"(?:khoảng|tầm|xấp xỉ|xap xi|cỡ|chừng|quanh)"
_TU_DEM = r"(?:\s*(?:giá|gia|mức\s*giá|mức|muc|giá\s*tiền|tiền))?"
_QUANH = re.compile(rf"{_TU_CHI_MUC}{_TU_DEM}\s*{_TIEN}", re.IGNORECASE)
# Biên độ cho "khoảng X": ±200 triệu. Đây là tham số TRẢI NGHIỆM do người dùng
# sản phẩm chốt, không phải con số lấy từ dữ liệu — đổi ở đây, một chỗ duy nhất.
_BIEN_DO_QUANH_TY = 0.2
_RE_NHAT = re.compile(r"rẻ nhất|thấp nhất|giá tốt nhất", re.IGNORECASE)
_DAT_NHAT = re.compile(r"đắt nhất|cao nhất", re.IGNORECASE)

# Diện tích — cùng bốn cách nói với giá. Đơn vị bắt buộc nên không cần từ đệm:
# "khoảng 43m²", "từ 40 đến 50 m2", "trên 60m2", "dưới 50 m²".
_DT_KHOANG = re.compile(rf"(?:từ\s*)?(\d[\d.,]*)\s*(?:-|–|—|đến|tới)\s*{_DT}", re.IGNORECASE)
_DT_QUANH = re.compile(rf"{_TU_CHI_MUC}(?:\s*(?:diện\s*tích|dien\s*tich))?\s*{_DT}", re.IGNORECASE)
_DT_DUOI = re.compile(rf"(?:dưới|nhỏ hơn|ít hơn|thấp hơn|không quá|tối đa|<=?)\s*{_DT}", re.IGNORECASE)
_DT_TREN = re.compile(rf"(?:trên|lớn hơn|rộng hơn|hơn|từ|tối thiểu|ít nhất|>=?)\s*{_DT}", re.IGNORECASE)
_DT_TRAN = re.compile(_DT, re.IGNORECASE)
# Biên độ cho "khoảng 43m²": ±3 m². Đủ để gom 43 và 45 m² lại — hai con số cùng
# nghĩa với người mua — mà không kéo sang loại căn khác.
_BIEN_DO_QUANH_M2 = 3.0

# Dưới ngưỡng này mà không có đơn vị thì hiểu là "tỷ" (người dùng gõ "dưới 3").
# Trên ngưỡng thì chắc chắn là đồng ("5.000.000.000").
_NGUONG_VND = 10_000


def _doc_so(text: str) -> float | None:
    """Đọc số theo quy ước Việt Nam: dấu phẩy là thập phân, dấu chấm ngăn nghìn.

    Nhờ vậy "2,5" = 2.5 còn "5.000.000.000" = 5000000000. Dữ liệu thật cũng ghi
    kiểu này — cột giá có "2,120 tỷ" nghĩa là 2.12 tỷ.
    """
    sach = text.replace(".", "").replace(",", ".")
    try:
        return float(sach)
    except ValueError:
        return None


def _doc_tien(so_text: str, don_vi: str | None) -> float | None:
    """Đổi một số tiền bất kỳ về đơn vị TỶ đồng."""
    so = _doc_so(so_text)
    if so is None:
        return None

    dv = (don_vi or "").lower()
    if dv in ("tỷ", "ty"):
        return so
    if dv in ("triệu", "trieu", "tr"):
        return so / 1_000
    if dv in ("đồng", "dong", "vnd", "vnđ"):
        return so / 1_000_000_000

    # Không có đơn vị: số to là đồng, số nhỏ là tỷ.
    return so / 1_000_000_000 if so >= _NGUONG_VND else so


def _rut_gia(query: str, criteria: dict[str, Any]) -> None:
    """Đọc khoảng giá từ câu hỏi.

    Thứ tự xét có chủ đích: khoảng hai đầu → "khoảng X" → một đầu. Câu "từ 2 đến
    3 tỷ" chứa cả "từ" lẫn "đến" nên nếu xét một đầu trước thì nó bắt nhầm.
    """
    khoang = _KHOANG.search(query)
    if khoang:
        # Vế đầu thường thiếu đơn vị ("từ 2 đến 3 tỷ") — mượn đơn vị của vế sau.
        thap = _doc_tien(khoang.group(1), khoang.group(2) or khoang.group(4))
        cao = _doc_tien(khoang.group(3), khoang.group(4))
        if thap is not None and cao is not None:
            criteria["price_min"], criteria["price_max"] = thap, cao
            return

    quanh = _QUANH.search(query)
    if quanh:
        moc = _doc_tien(quanh.group(1), quanh.group(2))
        if moc is not None:
            # Làm tròn 3 chữ số — đúng độ chính xác của cột giá (2,650 tỷ). Không
            # tròn thì 0,1 + 0,2 ra 0,30000000000000004 và con số đó đi thẳng lên
            # URL của portal.
            criteria["price_min"] = round(max(0.0, moc - _BIEN_DO_QUANH_TY), 3)
            criteria["price_max"] = round(moc + _BIEN_DO_QUANH_TY, 3)
            return

    _rut_mot_dau(query, criteria, _DUOI_NGHIEM, "price_max", nghiem_ngat=True)
    _rut_mot_dau(query, criteria, _DUOI_BAO_GOM, "price_max", nghiem_ngat=False)
    _rut_mot_dau(query, criteria, _TREN_NGHIEM, "price_min", nghiem_ngat=True)
    _rut_mot_dau(query, criteria, _TREN_BAO_GOM, "price_min", nghiem_ngat=False)


def _rut_dien_tich(query: str, criteria: dict[str, Any]) -> str:
    """Đọc khoảng diện tích. Trả về câu đã XOÁ phần nói về diện tích.

    Cùng thứ tự xét với giá, vì cùng cách nói.

    Phải chạy TRƯỚC `_rut_gia` và trả câu đã xoá, không thì hai bên tranh nhau
    cùng một con số: "căn từ 40 đến 50 m2" có `từ 40` khớp luôn mẫu giá cận
    dưới, và tiêu chí lòi ra thêm `price_min = 40` tỷ.

    Trước đây không có hàm này: "43m²" chỉ có hai kết cục, hoặc bị đọc thành 43
    TỶ, hoặc rơi ra ngoài hoàn toàn — cả hai đều dẫn tới "chưa đủ dữ liệu" trong
    khi kho có 6 căn 43 m² ở Ocean Park 1.
    """

    def _xoa(span: tuple[int, int]) -> str:
        return query[: span[0]] + " " + query[span[1] :]

    khoang = _DT_KHOANG.search(query)
    if khoang:
        thap, cao = _doc_so(khoang.group(1)), _doc_so(khoang.group(2))
        if thap is not None and cao is not None:
            criteria["area_min"], criteria["area_max"] = thap, cao
            return _xoa(khoang.span())

    quanh = _DT_QUANH.search(query)
    if quanh:
        moc = _doc_so(quanh.group(1))
        if moc is not None:
            criteria["area_min"] = round(max(0.0, moc - _BIEN_DO_QUANH_M2), 1)
            criteria["area_max"] = round(moc + _BIEN_DO_QUANH_M2, 1)
            return _xoa(quanh.span())

    con_lai = query
    for mau, khoa in ((_DT_DUOI, "area_max"), (_DT_TREN, "area_min")):
        khop = mau.search(con_lai)
        if khop:
            so = _doc_so(khop.group(1))
            if so is not None:
                criteria[khoa] = so
                con_lai = con_lai[: khop.start()] + " " + con_lai[khop.end() :]
    if con_lai != query:
        return con_lai

    # "Tìm căn 43m2 ở Ocean Park 1" — không từ chỉ mức nào, chỉ một con số trần.
    # Hiểu như "khoảng": người mua nói diện tích là nói mức mong muốn, không ai
    # đòi đúng 43,00 m².
    tran = _DT_TRAN.search(query)
    if tran:
        moc = _doc_so(tran.group(1))
        if moc is not None:
            criteria["area_min"] = round(max(0.0, moc - _BIEN_DO_QUANH_M2), 1)
            criteria["area_max"] = round(moc + _BIEN_DO_QUANH_M2, 1)
            return _xoa(tran.span())
    return query


def _rut_mot_dau(
    query: str,
    criteria: dict[str, Any],
    mau: re.Pattern[str],
    khoa: str,
    *,
    nghiem_ngat: bool,
) -> None:
    """Đặt một cận giá, kèm cờ cho biết cận đó có tính biên hay không.

    Không ghi đè cận đã đặt: "dưới 3 tỷ" và "không quá 3 tỷ" cùng nhắm
    `price_max`, mẫu nghiêm ngặt xét trước nên nó thắng — đúng với cách người
    dùng nói, "dưới" chặt hơn "không quá".
    """
    if khoa in criteria:
        return
    khop = mau.search(query)
    if khop is None:
        return
    gia = _doc_tien(khop.group(1), khop.group(2))
    if gia is None:
        return
    criteria[khoa] = gia
    if nghiem_ngat:
        criteria[f"{khoa}_nghiem_ngat"] = True


def extract_criteria(query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Rút tiêu chí lọc từ câu hỏi. Trả None nghĩa là tool không nên chạy.

    Tiêu chí trong CÂU HIỆN TẠI luôn thắng tiêu chí kế thừa từ lịch sử: người
    dùng vừa gõ ra điều gì thì đó là điều họ muốn bây giờ. Thực thể chỉ lấp chỗ
    trống — nhờ vậy "liệt kê 20 căn đó" (không tiêu chí nào trong câu) chạy được,
    còn "đổi sang Ocean Park 2 đi" thì phân khu mới đè lên phân khu cũ.
    """
    # Bỏ phần ngữ cảnh do giao diện chèn TRƯỚC khi soi mã căn. Mã căn trong đó
    # là căn người dùng đang mở, không phải căn họ đang hỏi.
    loi_nguoi_dung = bo_ngu_canh_giao_dien(query)

    if _UNIT_CODE.search(loi_nguoi_dung) or ma_can_tu_thuc_the(entities):
        return None  # Đang nói về căn cụ thể -> việc của inventory_lookup / so_sanh_can

    query = loi_nguoi_dung
    values = vocabulary.get()
    criteria: dict[str, Any] = {}

    # Diện tích trước, rồi mới giá — xem docstring `_rut_dien_tich`.
    _rut_gia(_rut_dien_tich(query, criteria), criteria)

    if _RE_NHAT.search(query):
        criteria["sort"] = "gia_tang"
        criteria.setdefault("limit", 3)
    elif _DAT_NHAT.search(query):
        criteria["sort"] = "gia_giam"
        criteria.setdefault("limit", 3)

    unit_type = _match_unit_type(query, values.get("unit_type", []))
    if unit_type:
        criteria["unit_type"] = unit_type

    # Đọc RỜI khỏi `unit_type`. Chuỗi trong DB gộp cả hai ("2PN, 1WC") nhưng
    # `unit_type` khớp theo tiền tố, nên gộp số vệ sinh vào đó thì "căn 2 vệ
    # sinh" — không nêu phòng ngủ — không có cách nào diễn đạt.
    so_wc = _WC.search(query)
    if so_wc:
        criteria["wc"] = int(so_wc.group(1))

    building = _match_building(query, values.get("building", []))
    if building:
        criteria["building"] = building

    direction = _match_direction(query, values.get("direction", []))
    if direction:
        criteria["direction"] = direction

    view = _VIEW.search(query)
    if view:
        criteria["view_keyword"] = view.group(1).strip()

    # Phải xét SAU toà nhà: mã toà "S2", "H1", "M3" chứa chữ số nhưng không phải
    # số phân khu. `_match_building` khớp theo token nên "S2" thành building, còn
    # `_PHAN_KHU` đòi có từ dẫn ("Ocean Park", "OP", "khu") nên không bắt nhầm.
    phan_khu = doc_phan_khu(query)
    if phan_khu:
        criteria["subdivision"] = phan_khu

    # Lấp chỗ trống bằng thực thể kế thừa. `setdefault` chứ không `update`:
    # câu hiện tại đã nêu gì thì giữ nguyên cái đó.
    for khoa, gia_tri in tieu_chi_tim(entities).items():
        criteria.setdefault(khoa, gia_tri)

    if la_cau_hoi_dem(loi_nguoi_dung) and not set(criteria) - _SUMMARY_LO_DUOC:
        # Câu ĐẾM mà `inventory_summary` lọc được hết tiêu chí thì nhường hẳn.
        # Chạy cả hai chỉ đặt một con số tổng hợp cạnh vài căn lấy mẫu, và dòng
        # "Nguồn" của câu trả lời "còn 30 căn" hoá ra ba mã căn ngẫu nhiên —
        # không mã nào là bằng chứng cho con số 30.
        #
        # Chỉ nhường khi summary lọc ĐƯỢC HẾT: nó không biết giá lẫn diện tích,
        # nên "có bao nhiêu căn dưới 4 tỷ" mà nhường thì con số trả về là đếm cả
        # kho, sai mà nghe rất chắc chắn.
        return None

    return criteria or None


def doc_phan_khu(query: str) -> str | None:
    """Tên phân khu nêu trong câu hỏi, hoặc None.

    Công khai vì `inventory_summary` dùng chung: hai tool phải hiểu câu hỏi
    GIỐNG HỆT nhau. Mỗi bên một luật thì chúng trả hai con số khác nhau cho
    cùng một câu, cả hai cùng nằm trong ngữ cảnh, và model chọn bừa một cái —
    đo được: "phân khu 3 còn bao nhiêu căn" trả lời 97 thay vì 30.
    """
    khop = _PHAN_KHU.search(query)
    return f"Ocean Park {khop.group(1)}" if khop else None


def chuan_hoa(text: str) -> str:
    """Bỏ dấu, khoảng trắng, dấu câu — để so khớp không phụ thuộc cách gõ."""
    return _fold(text)


class SearchArgs(BaseModel):
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN' hoặc 'Studio'")
    # Trường RIÊNG chứ không gộp vào `unit_type`. Dữ liệu ghi chung một chuỗi
    # ("2PN, 1WC") nên gộp thì chỉ hỏi được "2 phòng ngủ 1 vệ sinh"; hỏi riêng
    # "căn 2 vệ sinh" không diễn đạt nổi vì `unit_type` khớp theo TIỀN TỐ.
    wc: int | None = Field(default=None, ge=1, le=9, description="Số nhà vệ sinh, ví dụ 2")
    subdivision: str | None = Field(
        default=None, description="Phân khu: 'Ocean Park 1', 'Ocean Park 2' hoặc 'Ocean Park 3'"
    )
    building: str | None = Field(default=None, description="Toà nhà, ví dụ 'S210'")
    direction: str | None = Field(default=None, description="Hướng, ví dụ 'Đông Nam'")
    view_keyword: str | None = Field(default=None, description="Từ khoá trong mô tả view, ví dụ 'biển'")
    price_min: float | None = Field(default=None, ge=0, description="Giá tối thiểu, đơn vị TỶ đồng")
    price_max: float | None = Field(default=None, ge=0, description="Giá tối đa, đơn vị TỶ đồng")
    price_min_nghiem_ngat: bool = Field(
        default=False, description="True khi người dùng nói 'trên X' — loại luôn căn giá đúng X"
    )
    price_max_nghiem_ngat: bool = Field(
        default=False, description="True khi người dùng nói 'dưới X' — loại luôn căn giá đúng X"
    )
    area_min: float | None = Field(default=None, ge=0, description="Diện tích tối thiểu, m2")
    area_max: float | None = Field(default=None, ge=0, description="Diện tích tối đa, m2")
    sort: Literal["gia_tang", "gia_giam", "dien_tich_tang", "dien_tich_giam"] | None = Field(
        default=None,
        description="Thứ tự sắp xếp. Dùng 'gia_tang' cho câu hỏi 'rẻ nhất'.",
    )
    # Không đặt trần ở schema: model hay xin `limit: 100` cho câu "liệt kê hết",
    # và trần ở đây biến việc đó thành lỗi validation làm HỎNG CẢ TOOL — agent
    # mất luôn dữ liệu thay vì nhận danh sách ngắn. Cắt bớt trong `run()` bằng
    # MAX_RESULTS, kèm `ghi_chu` nói rõ tổng thật là bao nhiêu.
    limit: int | None = Field(default=None, ge=1, description="Số căn tối đa muốn xem")


def _so(gia_tri: Any) -> float | None:
    """Đổi Decimal/str từ DB thành float. Không đọc được thì trả None.

    None nghĩa là "không rõ giá" — khác hẳn 0. Căn không rõ giá bị loại khỏi bộ
    lọc khoảng giá thay vì bị coi là 0 đồng rồi lọt vào mọi câu "dưới X tỷ".
    """
    if gia_tri is None:
        return None
    try:
        return float(gia_tri)
    except (TypeError, ValueError):
        return None


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=extract_criteria)
class InventorySearchTool(AgentTool):
    """Tìm căn còn bán theo tiêu chí."""

    name = "inventory_search"
    # Bình thường nguồn là từng MÃ CĂN, nên nhãn này gần như không dùng tới.
    # Nó cứu đúng một ca: tra xong KHÔNG có căn nào khớp — lúc đó không mã căn
    # nào để trỏ vào, mà khẳng định "kho không có căn như vậy" vẫn cần chứng
    # minh. Thiếu nhãn thì `_nguon_cua_tool` rơi về tên tool và dòng "Nguồn"
    # hiện "inventory_search", một cái tên máy bấm vào không ra gì.
    nhan_nguon = "Dữ liệu tồn kho"
    description = (
        "Tìm danh sách căn hộ CÒN BÁN theo tiêu chí: số phòng ngủ, toà nhà, hướng, view, "
        "KHOẢNG GIÁ (tỷ đồng) và KHOẢNG DIỆN TÍCH (m2). Sắp xếp được theo giá hoặc diện tích "
        "nên trả lời được cả 'căn rẻ nhất'. Dùng khi người dùng mô tả căn muốn tìm mà không nêu mã căn."
    )
    args_schema = SearchArgs

    def _khong_khop(self, rows: list[dict[str, Any]], args: SearchArgs) -> dict[str, Any]:
        """Không có căn nào khớp — trả về KẾT LUẬN, không trả về rỗng.

        `data=[]` từng là câu trả lời ở đây, và nó gây một lỗi nhìn rất tệ:
        `ToolsNode` bỏ qua kết quả rỗng y hệt lúc không tool nào chạy, nên
        `generate` mất sạch bằng chứng, rơi xuống tài liệu, rồi guardrail trả
        "chưa đủ dữ liệu". Hỏi "căn 2 phòng ngủ 3 vệ sinh ở Ocean Park 1" thì
        trợ lý xin thêm dữ liệu tồn kho — trong khi nó VỪA tra xong kho và biết
        chắc chắn là không có.

        "Đã tra hết kho và không có" là một sự thật, không phải thiếu thông tin.

        Kèm theo những giá trị ĐANG CÓ sau khi nới hai tiêu chí hình dạng căn
        (`unit_type`, `wc`) để model nói được câu hữu ích — "Ocean Park 1 chỉ có
        loại 1 và 2 vệ sinh" — thay vì một lời từ chối cụt.
        """
        noi_long = args.model_copy(update={"unit_type": None, "wc": None})
        con_lai = self._filter(rows, noi_long)
        loai_dang_co = sorted({str(r.get("unit_type") or "").strip() for r in con_lai if r.get("unit_type")})

        data: dict[str, Any] = {
            "tong_so_khop": 0,
            "ket_luan": (
                "Đã tra HẾT kho và KHÔNG có căn nào khớp. Đây là kết luận chắc chắn, "
                "KHÔNG phải thiếu dữ liệu — đừng hỏi xin thêm thông tin tồn kho."
            ),
        }
        if loai_dang_co:
            data["loai_can_dang_co"] = loai_dang_co
            data["goi_y_noi_tieu_chi"] = (
                "Nói cho khách biết những loại căn đang có ở trên để họ chọn lại, "
                "chỉ dựa vào danh sách này, không suy đoán thêm."
            )
        return data

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            # Chỉ `sort` và `limit` được phép bỏ — chúng đổi CÁCH TRÌNH BÀY chứ
            # không đổi tập căn khớp. Trường lọc (`price_max`, `unit_type`…) sai
            # thì phải hỏng to tiếng: bỏ chúng đi là âm thầm nới rộng câu hỏi.
            args, bo_qua = doc_tham_so(SearchArgs, kwargs, co_the_bo={"sort", "limit"})
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        try:
            # CHỈ đẩy `building` xuống SQL. Loại căn lọc ở Python bằng _fold:
            # `query_units` dùng ILIKE nên '%2PN%' bỏ sót căn ghi '2 PN, 1WC'.
            # Dữ liệu hiện đã chuẩn hoá, nhưng tool không được phụ thuộc vào
            # việc dữ liệu mãi mãi sạch — bỏ sót căn là hỏng câm, không báo lỗi.
            rows = await asyncio.to_thread(
                get_inventory_db().query_units,
                building=args.building,
            )
        except Exception as exc:  # noqa: BLE001 - lỗi DB, không làm đứt luồng agent
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        khop = self._filter(rows, args)
        if not khop:
            # ⚠️ Phân biệt "lọc xong không còn căn nào" với "kho rỗng từ đầu".
            #
            # Chỉ ca thứ nhất mới được kết luận chắc chắn. Kho rỗng nghĩa là
            # `database_url` rơi về `sqlite:///./data/app.db` — một file rỗng
            # trong container khi thiếu biến môi trường (xem render.yaml). Lúc
            # đó tuyên bố "đã tra hết kho và không có căn nào" là nói chắc chắn
            # một điều SAI, tệ hơn hẳn việc nhận chưa đủ dữ liệu.
            data = self._khong_khop(rows, args) if rows else []
            return ToolResult(
                ok=True,
                data=data,
                source="inventory:postgres",
                error="Không có căn nào còn bán khớp tiêu chí.",
            )
        rows = khop

        hien = [_gon(r) for r in rows[: min(args.limit or MAX_RESULTS, MAX_RESULTS)]]

        # Khoá `can_hien_thi` cố ý KHÔNG tên là "danh_sach". Model đọc
        # `tong_so_khop` 21 cạnh một mảng tên `danh_sach` có 8 phần tử vẫn trả
        # lời "8 căn" — và nó không sai, mảng tên vậy thì nghĩa đen là danh sách.
        # "Căn hiển thị" nói đúng bản chất: đây là phần đem ra cho xem, không
        # hứa là tất cả. `day_du` trả lời câu đó tường minh.
        data: dict[str, Any] = {
            "tong_so_khop": len(rows),
            "day_du": len(hien) == len(rows),
            "can_hien_thi": hien,
        }
        if bo_qua:
            # Cho model biết tiêu chí nào đã bị bỏ, để nó đừng khẳng định đã lọc
            # theo thứ mà thực tế không lọc.
            data["tieu_chi_bo_qua"] = bo_qua
        if not data["day_du"]:
            data["ghi_chu"] = (
                f"Có TẤT CẢ {len(rows)} căn khớp tiêu chí; `can_hien_thi` chỉ là {len(hien)} căn đầu. "
                f"Hỏi SỐ LƯỢNG thì trả lời {len(rows)}, đừng đếm số phần tử trong mảng."
            )

        return ToolResult(ok=True, data=data, source="inventory:postgres")

    def _filter(self, rows: list[dict[str, Any]], args: SearchArgs) -> list[dict[str, Any]]:
        """Lọc mọi tiêu chí trừ toà nhà, dùng chung một phép so đã chuẩn hoá.

        Gom về một chỗ để không có hai luật khớp khác nhau (SQL một kiểu, Python
        một kiểu) rồi lệch nhau lúc dữ liệu ghi không thống nhất.
        """
        # Bỏ căn ĐÃ BÁN, giữ căn đang có người giữ chỗ / đã đặt cọc.
        #
        # Cọc có thể huỷ, nên giấu hẳn là chào thiếu hàng. Và khách đang xem dở
        # một căn rồi quay lại thấy nó biến mất mà không lời giải thích thì tệ
        # hơn là thấy nó kèm nhãn "Đã đặt cọc". `_gon` đính `status_label` vào
        # từng dòng để model nói được điều đó ra; các tool đếm thì không tính
        # chúng vào "đang bán".
        result = [r for r in rows if str(r.get("status") or "") != tt.DA_BAN]

        if args.subdivision:
            # So sau khi chuẩn hoá: dữ liệu ghi "Ocean Park 2" còn model có thể
            # gửi "OceanPark 2" hay "ocean park 2".
            wanted = _fold(args.subdivision)
            result = [r for r in result if _fold(str(r.get("subdivision") or "")) == wanted]

        if args.unit_type:
            wanted = _fold(args.unit_type)
            result = [r for r in result if _fold(str(r.get("unit_type") or "")).startswith(wanted)]

        if args.wc is not None:
            # Số vệ sinh nằm ở ĐUÔI chuỗi ("2PN, 1WC" -> "2PN1WC"). Dùng
            # `endswith` chứ không `in`: "1WC" nằm lọt trong "11WC" nếu có căn
            # nào ghi kiểu đó, và tìm 1 vệ sinh mà trả căn 11 vệ sinh thì sai.
            duoi = f"{args.wc}WC"
            result = [r for r in result if _fold(str(r.get("unit_type") or "")).endswith(duoi)]

        if args.direction:
            wanted = _fold(args.direction)
            result = [r for r in result if wanted in _fold(str(r.get("direction") or ""))]

        if args.view_keyword:
            wanted = _fold(args.view_keyword)
            result = [r for r in result if wanted in _fold(str(r.get("view") or ""))]

        result = self._loc_khoang(
            result,
            "price_value",
            args.price_min,
            args.price_max,
            thap_nghiem_ngat=args.price_min_nghiem_ngat,
            cao_nghiem_ngat=args.price_max_nghiem_ngat,
        )
        result = self._loc_khoang(result, "area_value", args.area_min, args.area_max)
        return self._sap_xep(result, args.sort)

    @staticmethod
    def _loc_khoang(
        rows: list[dict[str, Any]],
        cot: str,
        thap: float | None,
        cao: float | None,
        *,
        thap_nghiem_ngat: bool = False,
        cao_nghiem_ngat: bool = False,
    ) -> list[dict[str, Any]]:
        """Lọc theo khoảng số. Mặc định tính cả hai biên.

        Biên nghiêm ngặt chỉ bật khi người dùng nói "dưới X" / "trên X" — tiếng
        Việt phân biệt rõ với "không quá X". Kho hiện có 4 căn giá đúng 3 tỷ nên
        khác biệt này đếm được: "dưới 3 tỷ" ra 21 căn, "không quá 3 tỷ" ra 25.

        Trước đây luôn tính cả biên để khớp bộ lọc "Từ – Đến" trên portal. Nay
        cờ nghiêm ngặt được đẩy sang portal qua `priceMaxExclusive`, nên hai bên
        vẫn ra cùng một con số mà không phải hy sinh nghĩa của câu hỏi.

        Căn không rõ số bị loại chứ không đoán thành 0.
        """
        if thap is None and cao is None:
            return rows

        giu = []
        for r in rows:
            v = _so(r.get(cot))
            if v is None:
                continue
            if thap is not None and (v < thap or (thap_nghiem_ngat and v == thap)):
                continue
            if cao is not None and (v > cao or (cao_nghiem_ngat and v == cao)):
                continue
            giu.append(r)
        return giu

    @staticmethod
    def _sap_xep(rows: list[dict[str, Any]], sort: str | None) -> list[dict[str, Any]]:
        """Sắp xếp theo giá hoặc diện tích. Căn thiếu số xuống cuối, không lên đầu."""
        if not sort:
            return rows

        cot = "price_value" if sort.startswith("gia") else "area_value"
        giam = sort.endswith("_giam")
        vo_cuc = float("-inf") if giam else float("inf")
        return sorted(rows, key=lambda r: _so(r.get(cot)) if _so(r.get(cot)) is not None else vo_cuc, reverse=giam)
