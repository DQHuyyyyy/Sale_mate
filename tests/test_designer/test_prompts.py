"""Test bộ nạp prompt sửa ảnh.

Prompt nằm ở file .md và được tách theo tiêu đề `## `. Tách sai thì prompt gửi
model bị cụt hoặc lẫn khối của thao tác khác — mà lỗi ấy KHÔNG làm test nào đỏ
nếu không có file này, vì code vẫn chạy trơn và chỉ ảnh ra là sai.
"""

from __future__ import annotations

import pytest

from src.designer.editor import DOI_THUOC_TINH, THAO_TAC, XOA
from src.designer.prompts import khoi_sua_anh, load_khoi, load_prompt, prompt_dinh_vi


class TestTachKhoi:
    def test_co_du_khoi_chung_va_moi_thao_tac(self):
        """Thiếu khối cho một thao tác thì nó âm thầm rơi về `doi_thuoc_tinh` —
        yêu cầu "thêm cái tủ lạnh" sẽ nhận quy tắc "cấm vẽ thêm gì"."""
        assert set(khoi_sua_anh()) == {"chung", *THAO_TAC}

    def test_moi_khoi_deu_co_noi_dung(self):
        assert all(noi_dung.strip() for noi_dung in khoi_sua_anh().values())

    def test_khoi_khong_lan_tieu_de_cua_nhau(self):
        """Tách sai thì khối `xoa` nuốt luôn phần `thay_the` phía sau."""
        khoi = khoi_sua_anh()

        assert "## " not in khoi[XOA]
        assert "dựng lại nền phía sau" not in khoi[DOI_THUOC_TINH]

    def test_bo_phan_ghi_chu_truoc_tieu_de_dau_tien(self):
        """Đoạn `>` đầu file là ghi chú cho người đọc, không gửi model."""
        assert all("phiên bản v1" not in noi_dung for noi_dung in khoi_sua_anh().values())

    def test_tra_ve_dict_moi_moi_lan_goi(self):
        """Bên gọi lỡ sửa cũng không được làm hỏng prompt của lượt sau."""
        khoi_sua_anh()["chung"] = "đã bị sửa"

        assert khoi_sua_anh()["chung"] != "đã bị sửa"

    def test_file_khong_co_tieu_de_thi_tra_dict_rong(self):
        assert load_khoi("dinh_vi_v1") == {} or "## " in load_prompt("dinh_vi_v1")


class TestNoiDungBatBuoc:
    """Những dòng dưới đây là chốt an toàn — gỡ đi là ảnh vỡ trở lại."""

    @pytest.mark.parametrize(
        "cum_tu",
        ["KHÔNG để lại mảng đen", "vùng trong suốt", "trả lại ảnh gốc y nguyên", "Đúng phối cảnh"],
    )
    def test_khoi_chung_giu_du_cam_ky(self, cum_tu: str):
        assert cum_tu in khoi_sua_anh()["chung"]

    def test_moi_thao_tac_deu_nam_trong_danh_sach_hop_le(self):
        assert set(khoi_sua_anh()) - {"chung"} == set(THAO_TAC)


class TestPromptDinhVi:
    def test_doc_duoc_va_co_ba_thao_tac(self):
        noi_dung = prompt_dinh_vi()

        assert all(ten in noi_dung for ten in THAO_TAC)

    def test_nhac_toa_do_tuong_doi_va_goc_tren_trai(self):
        noi_dung = prompt_dinh_vi()

        assert "TƯƠNG ĐỐI" in noi_dung
        assert "TRÊN TRÁI" in noi_dung

    def test_cam_doi_cau_truc_can_ho(self):
        """Ảnh căn hộ thật đang rao bán — không dựng ra mặt bằng không có thật."""
        assert "cấu trúc căn hộ" in prompt_dinh_vi()


def test_thieu_file_prompt_thi_bao_loi_ro_rang():
    with pytest.raises(FileNotFoundError, match="Không tìm thấy prompt"):
        load_prompt("khong_ton_tai_v9")
