"""Cổng leo thang — quyết định có gọi orchestrator đắt tiền hay không.

## Nguyên tắc: quyết SAU khi có bằng chứng, không đoán TRƯỚC

Cách hay gặp là để router đoán trước độ khó rồi rẽ vào nhánh rẻ hay nhánh đắt.
Vấn đề không nằm ở việc có nhiều nhánh, mà ở THỜI ĐIỂM quyết: đoán sai vào
nhánh rẻ thì tool không chạy, và câu trả lời tệ đi mà không có dấu hiệu nào.

Dự án đã dính đúng lỗi đó một lần — "Ocean park có ưu đãi gì" bị xếp `general`
nên không truy hồi gì, và cách chữa là đảo `needs_retrieval` sang khai theo
LOẠI TRỪ (xem `nodes/router.py`).

Nên ở đây làm ngược lại: để đường tất định chạy trước, rồi mới đọc state xem nó
có gom được gì không. Đoán sai luật thì chỉ tốn vài xu, KHÔNG mất chất lượng —
đường rẻ đã chạy xong rồi.

## Ba luật, mỗi luật một cờ riêng

Tách cờ để tắt được từng cái khi thấy nó tốn tiền vô ích. Bật cả ba cùng lúc thì
lúc chi phí vọt lên không biết luật nào gây ra.

Không luật nào hỏi model "câu này có khó không". Tất cả đọc state đã có.
"""

from __future__ import annotations

from typing import Any

from src.agents.state import AgentState
from src.agents.thuc_the import ma_can, tieu_chi_tim
from src.core.logging import get_logger

logger = get_logger(__name__)

# Khoá thực thể thuộc miền TÀI CHÍNH. Có cả tiêu chí căn lẫn khoá ở đây nghĩa là
# câu hỏi cần một chuỗi tool phụ thuộc nhau: tìm căn trước, rồi mới tính vay
# theo giá của chính căn đó. `ToolsNode` chạy một nhịp nên không giải được.
_KHOA_TAI_CHINH = ("von_tu_co",)


def _r1_khong_du_bang_chung(state: AgentState, nguong_do_phu: float = 0.35) -> bool:
    """Cần tra cứu mà bằng chứng KHÔNG ĐỦ để trả lời.

    Đây đúng là nhánh `GuardrailNode` sẽ thay câu trả lời bằng "chưa đủ dữ liệu".
    Thay vì từ chối luôn, thử lại một lần bằng orchestrator — nó tự chọn tool và
    tự đặt tham số, nên bắt được ca mà `build_args` bằng regex bỏ lỡ.

    ⚠️ Phải dùng ĐÚNG phép kiểm của `GuardrailNode._has_enough_context`, không
    được tự nghĩ ra phép kiểm riêng. Bản đầu viết là "chunks rỗng" và đo trên
    máy thật thì gần như KHÔNG BAO GIỜ khớp: truy hồi luôn trả về top-N theo độ
    tương đồng bất kể có liên quan hay không, nên `chunks` hiếm khi rỗng — thứ
    quyết định từ chối là ĐỘ PHỦ dưới ngưỡng. Cổng bắn trượt đúng nhánh nó sinh
    ra để cứu, mà không có dấu hiệu gì ngoài việc chi phí Anthropic bằng 0.

    Hai bên hiểu "đủ dữ liệu" khác nhau là cách chắc chắn nhất để cổng vô dụng.
    """
    if not state.get("needs_retrieval"):
        return False
    if state.get("tool_context"):
        return False
    return not (bool(state.get("chunks")) and state.get("coverage", 0.0) >= nguong_do_phu)


def _r2_hai_mien_tieu_chi(state: AgentState) -> bool:
    """Vừa có tiêu chí căn vừa có tham số tài chính → chuỗi tool phụ thuộc."""
    entities = state.get("entities") or {}
    co_tieu_chi_can = bool(tieu_chi_tim(entities)) or bool(ma_can(entities))
    co_tai_chinh = any(entities.get(k) for k in _KHOA_TAI_CHINH)
    return co_tieu_chi_can and co_tai_chinh


def _r3_nhieu_ma_can_va_viec_khac(state: AgentState) -> bool:
    """Từ hai mã căn trở lên mà `so_sanh_can` không chạy.

    So sánh thuần đã có tool riêng lo. Còn "so sánh VOP345 với VOP397, căn nào
    vay lợi hơn" thì `so_sanh_can` trả bảng nhưng không ai tính vế tài chính —
    đúng chỗ cần một vòng lặp.
    """
    if len(ma_can(state.get("entities"))) < 2:
        return False
    return "so_sanh_can" not in (state.get("tools_ran") or [])


_LUAT = (
    ("R1", _r1_khong_du_bang_chung),
    ("R2", _r2_hai_mien_tieu_chi),
    ("R3", _r3_nhieu_ma_can_va_viec_khac),
)


def nen_leo_thang(
    state: AgentState,
    *,
    che_do: str = "khi_thieu",
    bat_r1: bool = True,
    bat_r2: bool = False,
    bat_r3: bool = False,
    nguong_do_phu: float = 0.35,
) -> str:
    """Tên luật đã khớp, hoặc chuỗi rỗng nếu không leo thang.

    Trả TÊN LUẬT chứ không trả bool: log và số đo cần biết luật nào kéo chi phí
    lên, nếu không thì lúc hết ngân sách chỉ biết "orchestrator chạy nhiều quá".

    ## Ba chế độ

    - `tat`      — không bao giờ. Đường tất định lo hết.
    - `khi_thieu`— chỉ khi một trong ba luật hẹp khớp.
    - `moi_luot` — MỌI câu cần dữ liệu. Orchestrator thành một tầng thật của
      agent chứ không phải lưới an toàn.

    ## Vì sao có `moi_luot`

    Bản đầu chỉ có `khi_thieu`, và đo trên máy thật thì nó khớp **0/8** câu điển
    hình: R1 đòi độ phủ dưới ngưỡng mà reranker cho điểm rộng tay, còn R2/R3 đọc
    thực thể vốn rỗng ở câu một lượt. Một tính năng không bao giờ chạy thì không
    khác gì không có.

    Bài học: **chạy rộng trước rồi thu hẹp theo số đo**, đừng thiết kế hẹp sẵn
    rồi hy vọng nó vừa. Hẹp quá thì không có dữ liệu nào để biết nên nới bao
    nhiêu; rộng quá thì bộ đếm ngân sách và log nói ngay cho biết phải siết.
    """
    if che_do == "tat":
        return ""

    if che_do == "moi_luot":
        # Câu xã giao vẫn không leo thang: không có gì để tra thì gọi model đắt
        # tiền chỉ để nghe nó nói "không cần tool nào" là tiêu tiền vô ích.
        if not state.get("needs_retrieval"):
            return ""
        logger.info("Leo thang: chế độ mọi lượt")
        return "MỌI-LƯỢT"

    dang_bat = {"R1": bat_r1, "R2": bat_r2, "R3": bat_r3}
    khop = {
        "R1": lambda s: _r1_khong_du_bang_chung(s, nguong_do_phu),
        "R2": _r2_hai_mien_tieu_chi,
        "R3": _r3_nhieu_ma_can_va_viec_khac,
    }
    for ten, _ in _LUAT:
        if dang_bat[ten] and khop[ten](state):
            logger.info("Leo thang theo luật %s", ten)
            return ten
    return ""


def mo_ta(state: AgentState) -> dict[str, Any]:
    """Luật nào khớp — kể cả luật đang tắt. Dùng để đo trước khi bật thật."""
    return {ten: luat(state) for ten, luat in _LUAT}
