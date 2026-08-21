"""Test việc giải tham chiếu bằng lịch sử và cách tool dùng thực thể.

Không gọi model. Hai thứ đáng test:

1. Lọc output thô của model — nó là thành phần xác suất, sẽ có lần trả khoá lạ
   hoặc mã căn bịa. Tầng lọc phải làm hậu quả vô hại.
2. Luật DANH TỪ kế thừa được / ĐỘNG TỪ thì không. Sai vế thứ hai là `dat_coc`
   ghi thêm lead mà khách không hề yêu cầu.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.state import Intent, initial_state
from src.agents.thuc_the import lam_sach, ma_can, tieu_chi_tim
from src.agents.tools import dat_coc, inventory, khoan_vay, search, so_sanh, summary
from src.agents.tools.registry import ToolBinding


class TestLamSach:
    def test_bo_khoa_la(self) -> None:
        assert lam_sach({"phan_khu": "Ocean Park 2", "khoa_bia": "x"}) == {"phan_khu": "Ocean Park 2"}

    def test_bo_gia_tri_rong(self) -> None:
        assert lam_sach({"phan_khu": "", "loai_can": None, "ma_can": []}) == {}

    def test_chi_nhan_ma_can_dung_dang(self) -> None:
        """Model hay trả "20 căn đó" hoặc "căn góc" — tra mã bịa tệ hơn không tra."""
        sach = lam_sach({"ma_can": ["VOP397", "20 căn đó", "căn góc", "vop345"]})

        assert sach["ma_can"] == ["VOP397", "VOP345"]

    def test_bo_hang_ma_can_khong_con_gi_thi_bo_luon_khoa(self) -> None:
        assert lam_sach({"ma_can": ["căn đó"]}) == {}

    def test_so_am_va_khong_hop_le_bi_bo(self) -> None:
        assert lam_sach({"gia_max": -1, "gia_min": "ba tỷ", "dien_tich_min": 65}) == {"dien_tich_min": 65.0}

    def test_khong_phai_dict_thi_tra_rong(self) -> None:
        assert lam_sach("['VOP397']") == {}
        assert lam_sach(None) == {}

    def test_doi_ten_tieu_chi_sang_tham_so_tool(self) -> None:
        ra = tieu_chi_tim({"phan_khu": "Ocean Park 1", "gia_max": 4.0, "loai_can": "2PN"})

        assert ra == {"subdivision": "Ocean Park 1", "price_max": 4.0, "unit_type": "2PN"}

    def test_tieu_chi_tim_khong_bao_gio_tra_ma_can(self) -> None:
        """Có mã căn là việc của inventory_lookup / so_sanh_can, không phải tìm kiếm."""
        assert "unit_code" not in tieu_chi_tim({"ma_can": ["VOP397"], "phan_khu": "Ocean Park 1"})

    def test_ma_can_luon_tra_list(self) -> None:
        assert ma_can(None) == []
        assert ma_can({}) == []
        assert ma_can({"ma_can": ["VOP1"]}) == ["VOP1"]


class TestRegistryThichUngChuKy:
    """Builder cũ chỉ nhận `query` phải chạy tiếp được — lời hứa "thêm tool là thêm một file"."""

    def test_builder_mot_tham_so_van_goi_duoc(self) -> None:
        binding = ToolBinding(intents=frozenset({Intent.LISTING}), build_args=lambda q: {"q": q})

        assert binding.dung_args("xin chào", {"phan_khu": "Ocean Park 1"}) == {"q": "xin chào"}

    def test_builder_hai_tham_so_nhan_duoc_thuc_the(self) -> None:
        binding = ToolBinding(
            intents=frozenset({Intent.LISTING}),
            build_args=lambda q, e: {"q": q, "e": e},
        )

        ra = binding.dung_args("x", {"phan_khu": "Ocean Park 3"})

        assert ra["e"] == {"phan_khu": "Ocean Park 3"}

    def test_khong_truyen_thuc_the_thi_thanh_dict_rong(self) -> None:
        binding = ToolBinding(
            intents=frozenset({Intent.LISTING}),
            build_args=lambda q, e: {"e": e},
        )

        assert binding.dung_args("x") == {"e": {}}


class TestDanhTuKeThuaDuoc:
    """Mã căn, phân khu, khoảng giá — thứ hội thoại đang nói ĐẾN."""

    def test_tim_kiem_dung_tieu_chi_luot_truoc(self) -> None:
        """Đây chính là ca "liệt kê 20 căn đó" từng rơi vào "chưa đủ dữ liệu"."""
        args = search.extract_criteria("liệt kê 20 căn đó", {"phan_khu": "Ocean Park 1", "gia_max": 4.0})

        assert args == {"subdivision": "Ocean Park 1", "price_max": 4.0}

    def test_khong_co_thuc_the_thi_van_tra_none_nhu_cu(self) -> None:
        assert search.extract_criteria("liệt kê 20 căn đó") is None

    def test_cau_hien_tai_thang_lich_su(self) -> None:
        """ "Đổi sang Ocean Park 2 đi" phải đè lên phân khu cũ, không phải trộn."""
        args = search.extract_criteria("còn Ocean Park 2 thì sao", {"phan_khu": "Ocean Park 1"})

        assert args["subdivision"] == "Ocean Park 2"

    def test_tra_mot_can_bang_ma_ke_thua(self) -> None:
        assert inventory._extract_args("căn đó còn không", {"ma_can": ["VOP397"]}) == {"unit_code": "VOP397"}

    def test_so_sanh_gop_ma_trong_cau_voi_ma_ke_thua(self) -> None:
        """ "so sánh nó với VOP893" chỉ nêu một mã, mã kia ở lượt trước."""
        args = so_sanh._rut_tham_so("so sánh nó với VOP893", {"ma_can": ["VOP619"]})

        assert set(args["unit_codes"]) == {"VOP893", "VOP619"}

    def test_dem_tong_hop_dung_phan_khu_ke_thua(self) -> None:
        args = summary._extract_args("vậy còn bao nhiêu căn", {"phan_khu": "Ocean Park 3"})

        assert args == {"subdivision": "Ocean Park 3"}

    def test_tinh_vay_lay_ca_ma_can_va_von_tu_lich_su(self) -> None:
        args = khoan_vay._rut_tham_so("thế vay được bao nhiêu", {"ma_can": ["VOP397"], "von_tu_co": 1.0})

        assert args == {"unit_code": "VOP397", "von_tu_co": 1.0}

    def test_dat_coc_lay_ma_can_tu_lich_su(self) -> None:
        args = dat_coc._rut_tham_so("chốt căn đó luôn nhé", {"ma_can": ["VOP345"]})

        assert args["unit_code"] == "VOP345"


class TestDongTuKhongKeThua:
    """Ý định phải đọc câu HIỆN TẠI. Kế thừa là chạy tool khách không yêu cầu."""

    def test_khong_hoi_vay_thi_khong_tinh_vay_du_du_du_kien(self) -> None:
        assert khoan_vay._rut_tham_so("căn đó hướng nào", {"ma_can": ["VOP397"], "von_tu_co": 1.0}) is None

    def test_khong_noi_dat_coc_thi_khong_ghi_lead(self) -> None:
        """Lượt 1 đặt cọc, lượt 3 hỏi hướng — không được ghi thêm lead lần nữa."""
        assert dat_coc._rut_tham_so("căn đó hướng nào", {"ma_can": ["VOP345"]}) is None

    def test_khong_co_dau_hieu_tong_hop_thi_khong_dem(self) -> None:
        assert summary._extract_args("căn đó đẹp không", {"phan_khu": "Ocean Park 1"}) is None

    @pytest.mark.parametrize("cau", ["xin chào", "cảm ơn bạn"])
    def test_cau_xa_giao_khong_kich_hoat_tool_nao(self, cau: str) -> None:
        thuc_the: dict[str, Any] = {"ma_can": ["VOP397"], "phan_khu": "Ocean Park 1", "von_tu_co": 1.0}

        assert dat_coc._rut_tham_so(cau, thuc_the) is None
        assert khoan_vay._rut_tham_so(cau, thuc_the) is None


class TestNhuongNhauGiuaBaToolTonKho:
    """Luật nhường nhau theo SỐ mã căn phải giữ nguyên khi mã đến từ lịch sử."""

    def test_mot_ma_ke_thua_thi_tim_kiem_im(self) -> None:
        assert search.extract_criteria("căn đó thế nào", {"ma_can": ["VOP397"]}) is None

    def test_hai_ma_ke_thua_thi_tra_mot_can_im(self) -> None:
        assert inventory._extract_args("hai căn đó", {"ma_can": ["VOP1", "VOP2"]}) is None

    def test_mot_ma_ke_thua_thi_so_sanh_im(self) -> None:
        assert so_sanh._rut_tham_so("căn đó", {"ma_can": ["VOP397"]}) is None


class TestStateCoThucThe:
    def test_luot_dau_thuc_the_rong(self) -> None:
        """Không có lịch sử thì không có gì để giải tham chiếu — hành vi y như cũ."""
        assert initial_state("xin chào", "s1").get("entities") in (None, {})
