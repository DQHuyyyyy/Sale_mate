"""Cửa sổ lịch sử của bộ giải tham chiếu, và ghi chú sắp xếp của inventory_search.

Hai lỗi này tìm được bằng eval, tái hiện 3/3, và cùng gây một triệu chứng: hỏi
"quay lại mấy căn 1PN lúc nãy, căn nào rẻ nhất?" sau vài lượt xen thì trợ lý trả
về căn ở SAI phân khu, rồi tự nhận chưa đủ dữ liệu để khẳng định.

Không test nào gọi model: cả hai chốt đều là hàm thuần.
"""

from __future__ import annotations

from src.agents.nodes.router import _SO_LUOT_NHIN_LAI, _THUC_THE_PROMPT, _tom_tat
from src.agents.tools.search import _ghi_chu_sap_xep
from src.models.chat import ChatMessage, MessageRole


def _lich_su_m03() -> list[ChatMessage]:
    """Đúng kịch bản M03: lập ngữ cảnh, ba lượt xen lạc đề, rồi hỏi lại."""
    cap = [
        ("Ocean Park 1 có căn 1PN nào không?", "Ocean Park 1 hiện có 11 căn 1PN trong dữ liệu tồn kho."),
        ("Chính sách hỗ trợ lãi suất hiện tại thế nào?", "Vinhomes khoá trần lãi suất 6%/năm trong 5 năm."),
        ("Từ Ocean Park 3 đi vào trung tâm Hà Nội mất bao lâu?", "Từ Ocean Park 3 vào trung tâm khoảng 30 phút."),
        ("Ocean Park 2 có những tiện ích nội khu gì?", "Ocean Park 2 có công viên, bể bơi và trường học."),
    ]
    ra: list[ChatMessage] = []
    for hoi, dap in cap:
        ra.append(ChatMessage(role=MessageRole.USER, content=hoi))
        ra.append(ChatMessage(role=MessageRole.ASSISTANT, content=dap))
    return ra


def test_cua_so_du_rong_de_thay_luot_lap_ngu_canh() -> None:
    """Cửa sổ 4 lượt cắt mất chính lượt nêu 'Ocean Park 1' — lỗi đã xảy ra thật.

    Model không thể giải tham chiếu về thứ nó không được nhìn thấy. Đây là chốt
    quan trọng hơn cả con số 10: hạ xuống dưới 8 là lỗi cũ quay lại.
    """
    tom_tat = _tom_tat(_lich_su_m03())

    assert "Ocean Park 1" in tom_tat
    assert _SO_LUOT_NHIN_LAI >= 8


def test_cua_so_van_giu_hai_luot_xen_gan_nhat() -> None:
    """Rộng thêm không được đánh mất lượt gần — 'căn đó' vẫn hay trỏ về lượt liền trước."""
    tom_tat = _tom_tat(_lich_su_m03())

    assert "Ocean Park 2" in tom_tat


def test_prompt_day_du_luat_chong_lay_nham_tieu_chi_gan_nhat() -> None:
    """Cửa sổ rộng chỉ an toàn nhờ luật trong prompt — gỡ luật là nới rủi ro."""
    assert "lúc nãy" in _THUC_THE_PROMPT
    assert "đổi sang" in _THUC_THE_PROMPT


def test_luot_dai_bi_cat_ngan_de_prompt_khong_phinh() -> None:
    dai = ChatMessage(role=MessageRole.ASSISTANT, content="x" * 5000)

    assert len(_tom_tat([dai])) < 1000


# ---------- Ghi chú sắp xếp ----------


def test_ghi_chu_noi_ro_phan_tu_dau_la_cuc_tri_cua_ca_tap() -> None:
    """Thiếu câu này thì model nói 'chưa đủ dữ liệu' dù đang cầm đúng câu trả lời."""
    ghi_chu = _ghi_chu_sap_xep("gia_tang", 12)

    assert "RẺ NHẤT" in ghi_chu
    assert "12" in ghi_chu


def test_khong_sap_xep_thi_khong_khang_dinh_gi() -> None:
    """Không có `sort` thì danh sách rút gọn KHÔNG phải cực trị — cấm nói bừa."""
    assert _ghi_chu_sap_xep(None, 12) == ""


def test_moi_kieu_sap_xep_co_nhan_rieng() -> None:
    assert "ĐẮT NHẤT" in _ghi_chu_sap_xep("gia_giam", 5)
    assert "NHỎ NHẤT" in _ghi_chu_sap_xep("dien_tich_tang", 5)
    assert "LỚN NHẤT" in _ghi_chu_sap_xep("dien_tich_giam", 5)
