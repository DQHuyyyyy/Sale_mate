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

from src.models.chat import Citation

# Lượt trả lời từ tài liệu giữ mấy nguồn. Truy hồi lấy về nhiều hơn thế, nhưng
# đuôi danh sách là chunk điểm thấp — liệt kê ra chỉ làm loãng.
TOI_DA_NGUON_TAI_LIEU = 3


def _khong_dau(chu: str) -> str:
    """Bỏ dấu và hạ chữ thường — so khớp tên tài liệu không kén cách gõ."""
    tach = unicodedata.normalize("NFD", chu.lower())
    return "".join(k for k in tach if unicodedata.category(k) != "Mn")


def _co_trong(nhan: str, cau_tra_loi: str) -> bool:
    """Nhãn nguồn có được nhắc trong câu trả lời không.

    Mã căn so theo ranh giới từ để "VOP61" không khớp nhầm vào "VOP619". Tên tài
    liệu dài nên so theo chuỗi con sau khi bỏ dấu.
    """
    if re.fullmatch(r"[A-Za-z]{2,4}\d{2,5}", nhan):
        return re.search(rf"\b{re.escape(nhan)}\b", cau_tra_loi, re.IGNORECASE) is not None
    return _khong_dau(nhan) in _khong_dau(cau_tra_loi)


def loc_nguon_da_dung(
    citations: list[Citation],
    cau_tra_loi: str,
    *,
    co_du_lieu_tool: bool,
) -> list[Citation]:
    """Bỏ nguồn chỉ 'đã tra' mà không 'đã dùng'. Giữ nguyên thứ tự."""
    if not cau_tra_loi.strip():
        # Chưa có chữ nào để đối chiếu (lỗi giữa chừng, hoặc đường không stream
        # gọi trước khi sinh). Thà giữ nguyên còn hơn xoá sạch nguồn.
        return citations

    co_nhan = [c for c in citations if (c.title or "").strip()]
    giu: list[Citation] = []
    tai_lieu_con_lai = TOI_DA_NGUON_TAI_LIEU

    for nguon in co_nhan:
        nhan = nguon.title.strip()
        if nguon.kind == "db" or co_du_lieu_tool:
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
    du_phong = [c for c in co_nhan if c.kind == "db"][:TOI_DA_NGUON_TAI_LIEU]
    return giu + du_phong
