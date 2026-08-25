"""Lọc nguồn: chỉ giữ thứ câu trả lời THẬT SỰ dùng.

Vì sao cần: hai đường sinh nguồn đều trả về "đã tra cứu", không phải "đã dùng".

- `RetrieveNode` tạo một `Citation` cho MỌI chunk lấy về, vô điều kiện. Vector
  search luôn trả đủ số chunk được hỏi, kể cả khi chỉ một cái liên quan.
- `ToolsNode` tạo nguồn cho mọi tool chạy được, kể cả tool không đóng góp gì vào
  câu chữ cuối cùng.

Hệ quả đã thấy trên production: hỏi "căn ở Ocean Park 1", trả lời ba căn OP1, mà
dòng nguồn liệt kê cả tổng quan OP2, OP3 và ưu đãi OP2 — những tài liệu vector
search có trả về nhưng model không hề dùng. Trích nguồn kiểu đó phản tác dụng:
nó vốn để chứng minh trợ lý không bịa, mà lại chỉ vào thứ không liên quan thì
người đọc mất niềm tin vào cả những nguồn đúng.

Luật ở đây cố ý ĐƠN GIẢN và kiểm chứng được, không đoán ý model:

- Nguồn dữ liệu (`kind="db"`, nhãn là mã căn): giữ nếu mã căn XUẤT HIỆN trong
  câu trả lời. Model nhắc căn nào thì căn đó là nguồn.
- Nguồn tài liệu (`kind="doc"`): lượt có dữ liệu tool thì các con số đến từ tool,
  tài liệu chỉ giữ khi model trích tên nó tường minh. Lượt không có tool thì câu
  trả lời chắc chắn dựng từ tài liệu, giữ vài cái điểm cao nhất.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from src.models.chat import Citation

# Lượt trả lời từ tài liệu giữ mấy nguồn. Truy hồi lấy về nhiều hơn thế, nhưng
# đuôi danh sách là chunk điểm thấp — liệt kê ra chỉ làm loãng.
TOI_DA_NGUON_TAI_LIEU = 3


def _khong_dau(chu: str) -> str:
    """Bỏ dấu và hạ chữ thường — so khớp tên tài liệu không kén cách gõ.

    `đ` thay tay vì NFD không tách nó ra `d`: nó là một ký tự riêng (U+0111),
    khác với ư, ã, ê… vốn là chữ cái cộng dấu tổ hợp.
    """
    tach = unicodedata.normalize("NFD", chu.lower().replace("đ", "d"))
    return "".join(k for k in tach if unicodedata.category(k) != "Mn")


# Nhãn hình mã căn: 2-4 chữ cái rồi 2-5 chữ số. Phân biệt nguồn TRỎ VÀO MỘT CĂN
# với nguồn tổng hợp ("Dữ liệu tồn kho") — hai loại chịu luật lọc khác nhau.
_LA_MA_CAN = re.compile(r"[A-Za-z]{2,4}\d{2,5}")


# Dấu trích model tự viết: `[Chính sách hỗ trợ lãi suất]`. Cùng cú pháp mà
# prompt dạy và FE gỡ khỏi thân bài.
_DAU_TRICH = re.compile(r"\[([^\]\n]{2,60})\]")

# Nhãn rút gọn phải dài tối thiểu ngần này ký tự (đã bỏ dấu và khoảng trắng) mới
# được coi là "gọi tên tài liệu". "chinhsachhotrolaisuat" (21) là gọi tên;
# "chinhsach" (9) thì khớp cả bảng giá lẫn chính sách bán hàng, nhận vào là mở
# đường cho nhãn sai.
_DAI_TOI_THIEU_NHAN_RUT_GON = 15


def _co_trong(nhan: str, cau_tra_loi: str) -> bool:
    """Nhãn nguồn có được nhắc trong câu trả lời không.

    Mã căn so theo ranh giới từ để "VOP61" không khớp nhầm vào "VOP619". Tên tài
    liệu dài nên so theo chuỗi con sau khi bỏ dấu.

    Tên tài liệu còn nhận cả bản RÚT GỌN model tự viết. Ca thật: tài liệu tên
    "Chính sách hỗ trợ lãi suất chung của Vinhomes" mà model trích
    `[Chính sách hỗ trợ lãi suất]` — thiếu bốn chữ cuối. Đòi tên đầy đủ nằm
    nguyên trong câu thì tài liệu bị loại, và câu trả lời nêu trần 6%/năm cùng
    các gói 18/24/30/36/60 tháng đứng đó không nguồn.

    Chỉ nhận rút gọn từ trong DẤU TRÍCH, không quét cả câu: "chính sách hỗ trợ
    lãi suất" nằm giữa một câu văn xuôi là model đang NÓI VỀ chính sách, chưa
    chắc đang trích nó.
    """
    if _LA_MA_CAN.fullmatch(nhan):
        return re.search(rf"\b{re.escape(nhan)}\b", cau_tra_loi, re.IGNORECASE) is not None

    tieu_de = _khong_dau(nhan)
    if tieu_de in _khong_dau(cau_tra_loi):
        return True

    return any(
        len(rut_gon := _khong_dau(m.group(1)).replace(" ", "")) >= _DAI_TOI_THIEU_NHAN_RUT_GON
        and rut_gon in tieu_de.replace(" ", "")
        for m in _DAU_TRICH.finditer(cau_tra_loi)
    )


# Câu trả lời mang nghĩa "mình không trả lời được". Model tự viết bằng lời của
# nó, không chỉ chép hằng `INSUFFICIENT_MESSAGE`, nên phải dò theo cụm từ.
_CUM_TU_CHOI = (
    "chưa có đủ dữ liệu",
    "chưa đủ dữ liệu",
    "không có đủ dữ liệu",
    "chưa có thông tin",
    "không có thông tin",
    "chưa tạo được câu trả lời",
    "cho mình thêm thông tin",
)

# Trên ngần này ký tự thì dù có cụm từ chối, câu trả lời vẫn đang nói một điều
# gì đó thật — thường là trả lời được phần lớn rồi ghi chú phần còn thiếu. Lời
# từ chối thuần thì ngắn: hai câu từ chối trong ca thật đo được 240 và 280 ký
# tự, còn câu trả lời có nội dung dài gấp đôi trở lên.
_DAI_TOI_DA_CUA_LOI_TU_CHOI = 400


def la_loi_tu_choi(cau_tra_loi: str) -> bool:
    """Câu trả lời có thực chất là lời từ chối không."""
    sach = cau_tra_loi.strip()
    if len(sach) > _DAI_TOI_DA_CUA_LOI_TU_CHOI:
        return False
    thap = _khong_dau(sach)
    return any(_khong_dau(cum) in thap for cum in _CUM_TU_CHOI)


# Con số CÓ ĐƠN VỊ — dấu hiệu câu trả lời đang khẳng định một điều lấy từ tool.
# Bắt buộc có đơn vị đi kèm vì chữ số trần xuất hiện khắp nơi vô hại: "Ocean
# Park 1", "OP3", "tòa S2". So trên chuỗi đã bỏ dấu nên chỉ cần viết dạng không
# dấu.
#
# ⚠️ CỐ Ý không có "phong ngu", "pn", "wc", "ve sinh". Chúng là TIÊU CHÍ người
# dùng nêu ra, và lời từ chối gần như luôn nhắc lại tiêu chí đó — "chưa đủ dữ
# liệu về căn 2 phòng ngủ và 3 vệ sinh" bị tính là khẳng định, nên nguồn không
# bị xoá và ba tài liệu vô can leo lên dòng "Nguồn". Đo được trên production.
#
# Giá, diện tích, phần trăm, số lượng căn thì khác: chúng là thứ hệ thống TRẢ
# VỀ, người dùng không tự nêu trong câu hỏi.
_SO_LIEU = re.compile(r"\d[\d.,]*\s*(ty\b|trieu\b|m2\b|m²|%|can\b)")

# Cách nói trỏ vào một căn cụ thể mà không nhắc mã — "Căn này giá 2,7 tỷ".
_TRO_VAO_CAN = ("can nay", "can do", "can tren", "can dau tien", "can thu")

# Mã căn trong câu trả lời. Nhắc đích danh một căn LÀ khẳng định, kể cả khi
# không kèm con số nào: "Căn VOP619 có 2 phòng ngủ, mình chưa có dữ liệu giá"
# là từ chối MỘT PHẦN và phần đã trả lời vẫn cần nguồn để kiểm.
_MA_CAN_TRONG_CAU = re.compile(r"\b[A-Z]{2,4}\d{2,5}\b")


def _co_khang_dinh_ve_can(cau_tra_loi: str) -> bool:
    """Câu trả lời có KHẲNG ĐỊNH gì cần chứng minh bằng dữ liệu tool không.

    Lưới an toàn bên dưới sinh ra để cứu ca "câu trả lời nói *căn này* thay vì
    nhắc mã" — số liệu vẫn từ tool nên xoá nguồn là xoá bằng chứng. Nhưng nó
    không phân biệt được với ca ngược lại: trợ lý HỎI NGƯỢC để làm rõ tiêu chí,
    chưa khẳng định gì cả.

    Ca thật: "Căn ở Ocean Park 1" → `inventory_search` chạy và trả 23 căn →
    trợ lý hỏi lại "bạn muốn lọc theo tiêu chí nào?" → không mã căn nào lọt bộ
    lọc → lưới an toàn dựng lên VOP758, VOP285, VOP619 dưới một câu hỏi không
    nhắc tới căn nào. Người đọc thấy ngay là sai, và mất tin vào cả dòng nguồn
    ở những lượt đúng.

    `_CUM_TU_CHOI` đã bắt một phần ca hỏi ngược ("cho mình thêm thông tin"),
    nhưng bắt theo cụm từ thì model đổi cách nói một chút là lọt. Ở đây hỏi
    thẳng vào thứ CẦN chứng minh: có số liệu, có mã căn, hoặc có trỏ vào một
    căn cụ thể.

    Số phòng ngủ và số vệ sinh KHÔNG tính — xem chú thích ở `_SO_LIEU`. Chúng
    là tiêu chí người dùng nêu, mà lời từ chối luôn nhắc lại tiêu chí.
    """
    thap = _khong_dau(cau_tra_loi)
    if _MA_CAN_TRONG_CAU.search(cau_tra_loi):
        return True
    return bool(_SO_LIEU.search(thap)) or any(cum in thap for cum in _TRO_VAO_CAN)


def _bo_trung(citations: Iterable[Citation]) -> list[Citation]:
    """Một TÀI LIỆU một dòng, dù nó đóng góp bao nhiêu đoạn. Giữ nguyên thứ tự.

    `RetrieveNode` tạo một `Citation` cho MỖI CHUNK, và truy hồi thường lấy 3-5
    đoạn của cùng một tài liệu — nên dòng "Nguồn" hiện y hệt một cái tên ba lần.
    Đã thấy thật: câu hỏi về chính sách lãi suất cho ra
    `"Chính sách hỗ trợ lãi suất chung của Vinhomes"` lặp ba lượt.

    Trùng ở đây là trùng NGUỒN, không phải trùng bằng chứng: ba đoạn của cùng
    một tài liệu vẫn chỉ trỏ về một chỗ để người đọc mở ra kiểm.

    Khử theo `doc_id` chứ không theo nhan đề: hai tài liệu khác nhau có thể
    trùng tên sau một lần đổi tên file, và `doc_id` mới là thứ nút bấm dùng.

    Xếp tài liệu đóng góp NHIỀU ĐOẠN NHẤT lên đầu. Người đọc nhìn dòng "Nguồn"
    có hai cái tên thì câu hỏi đầu tiên của họ là "tin cái nào" — thứ tự phải
    trả lời được câu đó.

    Vì sao đếm đoạn chứ không xếp theo điểm: `KeywordOverlapReranker` cho điểm
    rất phẳng. Đo thật với "tôi muốn vay 2 tỷ, thời hạn 3 năm" — tài liệu chính
    sách lãi suất được 0,650 còn tài liệu pháp lý được 0,620, gần như bằng nhau.
    Nhưng chính sách góp **4/5 đoạn** còn pháp lý góp **1/5**. Số đoạn nói rõ
    tài liệu nào thật sự dựng nên câu trả lời, điểm thì không.
    """
    dem: dict[tuple[str, str], int] = {}
    dau_tien: dict[tuple[str, str], Citation] = {}
    for c in citations:
        khoa = (c.doc_id or "", (c.title or "").strip())
        dem[khoa] = dem.get(khoa, 0) + 1
        dau_tien.setdefault(khoa, c)

    # `sorted` ổn định nên nhóm cùng số đoạn giữ nguyên thứ tự xuất hiện — mã căn
    # (mỗi căn đúng một citation) không bị xáo trộn.
    return [dau_tien[k] for k in sorted(dem, key=lambda k: -dem[k])]


def loc_nguon_da_dung(
    citations: list[Citation],
    cau_tra_loi: str,
    *,
    co_du_lieu_tool: bool,
) -> list[Citation]:
    """Bỏ nguồn chỉ 'đã tra' mà không 'đã dùng'. Giữ nguyên thứ tự."""
    # Từ chối mà vẫn trưng nguồn là tự phủ định trước mặt khách: "mình không có
    # dữ liệu" đứng ngay trên "nguồn: đúng tài liệu bạn đang hỏi". Ca thật đã
    # xảy ra và người dùng bắt được ngay — họ thấy trợ lý đang cầm đúng thứ họ
    # cần mà không chịu đưa.
    #
    # Nhưng chỉ khi câu đó KHÔNG khẳng định gì. Câu trả lời một PHẦN rất hay gặp
    # ở nhánh tính vay: "Căn VOP962 giá 2,7 tỷ. Vay 70% khoảng 1,89 tỷ. Mình
    # chưa có đủ dữ liệu về lãi suất để tính trả hàng tháng." — có cụm từ chối,
    # lại ngắn dưới ngưỡng 400 ký tự, nên `la_loi_tu_choi` gọi nó là từ chối và
    # xoá sạch nguồn. Hai con số vừa nêu mất chỗ dựa, đúng lúc chúng là thứ
    # khách sẽ mang đi hỏi ngân hàng.
    #
    # KHÔNG sửa `la_loi_tu_choi`: bộ eval dùng chung hàm đó để chấm cột
    # `phai_tu_choi`, đổi định nghĩa là đổi luôn số đo lịch sử. Ràng thêm điều
    # kiện tại chỗ này thì eval giữ nguyên nghĩa, còn dòng "Nguồn" phủ đúng thứ
    # câu trả lời khẳng định.
    if la_loi_tu_choi(cau_tra_loi) and not _co_khang_dinh_ve_can(cau_tra_loi):
        return []

    if not cau_tra_loi.strip():
        # Chưa có chữ nào để đối chiếu (lỗi giữa chừng, hoặc đường không stream
        # gọi trước khi sinh). Thà giữ nguyên còn hơn xoá sạch nguồn.
        return citations

    co_nhan = _bo_trung(c for c in citations if (c.title or "").strip())
    giu: list[Citation] = []
    tai_lieu_con_lai = TOI_DA_NGUON_TAI_LIEU

    for nguon in co_nhan:
        nhan = nguon.title.strip()
        if nguon.kind == "db" and not _LA_MA_CAN.fullmatch(nhan):
            # Nguồn TỔNG HỢP ("Dữ liệu tồn kho"): không có mã căn để đối chiếu
            # với câu chữ, nên luật "phải xuất hiện trong câu trả lời" không áp
            # dụng được. Bỏ vế này thì câu "còn 30 căn đang bán" mất sạch nguồn.
            giu.append(nguon)
        elif nguon.kind == "db" or co_du_lieu_tool:
            if _co_trong(nhan, cau_tra_loi):
                giu.append(nguon)
        elif tai_lieu_con_lai > 0:
            giu.append(nguon)
            tai_lieu_con_lai -= 1

    if any(c.kind == "db" for c in giu):
        return giu

    # Lượt có dữ liệu tool mà không nguồn tool nào lọt: câu trả lời nói về căn
    # nhưng không nhắc lại mã ("Căn này giá 2,7 tỷ"). Số liệu vẫn đến từ tool,
    # nên xoá sạch nguồn là xoá đúng thứ chứng minh trợ lý không bịa. Giữ lại
    # vài cái đầu — bớt ồn mà không mất bằng chứng.
    #
    # Trừ khi câu trả lời chưa khẳng định gì: không có gì để chứng minh thì
    # không có nguồn. Xem `_co_khang_dinh_ve_can`.
    if not _co_khang_dinh_ve_can(cau_tra_loi):
        return giu

    du_phong = [c for c in co_nhan if c.kind == "db"][:TOI_DA_NGUON_TAI_LIEU]
    return giu + du_phong
