"""Test tool đặt cọc — bước chốt của cả luồng tư vấn.

Hai thứ dễ hỏng nhất và phải giữ bằng test:

1. Tool phải chạy KHI CHƯA CÓ số điện thoại. Nếu không, câu "đặt cọc căn VOP397"
   rơi vào nhánh "chưa đủ dữ liệu" — khách bị từ chối đúng lúc muốn mua.
2. Tool KHÔNG được bịa điều khoản cọc. Hệ thống không có dữ liệu nào về số tiền
   cọc hay thời hạn giữ chỗ.
"""

from __future__ import annotations

import pytest

from src.agents.tools import dat_coc as mod_dat_coc
from src.agents.tools.dat_coc import DatCocTool, _rut_tham_so, chuan_hoa_sdt


def _luu() -> list[dict]:
    """Đọc lead qua ĐÚNG accessor mà conftest đã vá.

    Không `from src.data.stores.dat_coc_db import get_dat_coc_db` rồi gọi thẳng:
    hàm đó đọc `get_settings()` toàn cục, tức `.env` của máy, tức Supabase
    production. Viết test cho tool này đã tạo nhầm bảng thật một lần vì đúng
    dòng đó.
    """
    return mod_dat_coc.get_dat_coc_db().danh_sach()


class TestRutThamSo:
    def test_can_ca_y_dinh_coc_lan_ma_can(self) -> None:
        assert _rut_tham_so("đặt cọc thế nào") is None, "thiếu mã căn thì không chạy"
        assert _rut_tham_so("căn VOP397 giá bao nhiêu") is None, "chỉ hỏi giá thì không phải cọc"
        assert _rut_tham_so("đặt cọc căn VOP397") == {"unit_code": "VOP397"}

    def test_chua_co_so_dien_thoai_van_chay(self) -> None:
        """Chốt chặn quan trọng nhất: có chạy thì trợ lý mới có cớ hỏi xin số."""
        assert _rut_tham_so("Đặt cọc giữ chỗ căn VOP397") is not None

    def test_rut_duoc_ten_va_so_khi_khach_da_noi(self) -> None:
        args = _rut_tham_so("tôi muốn cọc căn VOP397, tên tôi là Nguyễn Văn A, số 0912 345 678")

        assert args == {
            "unit_code": "VOP397",
            "so_dien_thoai": "0912345678",
            "ho_ten": "Nguyễn Văn A",
        }

    def test_khong_doan_ten_tu_cau_tu_do(self) -> None:
        """Đoán tên từ câu không có từ dẫn là cách nhanh nhất để ghi sai tên khách."""
        args = _rut_tham_so("cọc căn VOP397 nhé bạn ơi 0912345678")

        assert args is not None
        assert "ho_ten" not in args

    @pytest.mark.parametrize(
        ("thô", "mong_doi"),
        [
            ("+84 912.345-678", "0912345678"),
            ("0912 345 678", "0912345678"),
            ("84912345678", "0912345678"),
            ("0912345678", "0912345678"),
        ],
    )
    def test_chuan_hoa_so_dien_thoai(self, thô: str, mong_doi: str) -> None:
        assert chuan_hoa_sdt(thô) == mong_doi


class TestChay:
    @pytest.mark.asyncio
    async def test_thieu_so_thi_bao_can_bo_sung_chu_khong_bao_loi(self) -> None:
        ket_qua = await DatCocTool().run(unit_code="VOP397")

        assert ket_qua.ok, "báo lỗi ở đây là đẩy khách vào nhánh từ chối"
        assert ket_qua.data["trang_thai"] == "can_bo_sung"
        assert "số điện thoại" in ket_qua.data["con_thieu"]

    @pytest.mark.asyncio
    async def test_khong_bia_dieu_khoan_coc(self) -> None:
        """Tiền thật của khách — đoán sai một con số là hỏng cả giao dịch."""
        ket_qua = await DatCocTool().run(unit_code="VOP397")

        chu = str(ket_qua.data).lower()
        assert "triệu" not in chu and "tỷ" not in chu and "%" not in chu

    @pytest.mark.asyncio
    async def test_so_khong_hop_le_thi_van_xin_lai(self) -> None:
        ket_qua = await DatCocTool().run(unit_code="VOP397", so_dien_thoai="123")

        assert ket_qua.data["trang_thai"] == "can_bo_sung"

    @pytest.mark.asyncio
    async def test_du_thong_tin_thi_ghi_lead(self) -> None:
        ket_qua = await DatCocTool().run(
            unit_code="vop397",
            so_dien_thoai="0912345678",
            ho_ten="Nguyễn Văn A",
        )

        assert ket_qua.data["trang_thai"] == "da_ghi_nhan"
        assert ket_qua.data["ma_can"] == "VOP397", "mã căn phải viết hoa cho khớp tồn kho"

        luu = _luu()
        assert len(luu) == 1
        assert luu[0]["so_dien_thoai"] == "0912345678"
        assert luu[0]["trang_thai"] == "new"

    @pytest.mark.asyncio
    async def test_khong_tra_lai_so_dien_thoai_vao_ngu_canh_model(self) -> None:
        """Số vào `data` là số đi vào prompt, rồi vào log của nhà cung cấp LLM."""
        ket_qua = await DatCocTool().run(unit_code="VOP397", so_dien_thoai="0912345678", ho_ten="A")

        assert "0912345678" not in str(ket_qua.data)

    @pytest.mark.asyncio
    async def test_goi_lai_trong_ngay_khong_tao_lead_trung(self) -> None:
        """Người dùng gõ lại câu cũ là chuyện thường, không phải hai khách."""
        for _ in range(2):
            ket_qua = await DatCocTool().run(unit_code="VOP397", so_dien_thoai="0912345678")

        assert ket_qua.data["trang_thai"] == "da_ghi_nhan_truoc_do"
        assert len(_luu()) == 1

    @pytest.mark.asyncio
    async def test_db_hong_thi_tra_failure_chu_khong_raise(self) -> None:
        """Tool không raise — một tool hỏng không được làm đứt cả lượt trả lời."""

        class _Hong(DatCocTool):
            def _ghi(self, args, sdt):  # type: ignore[override]
                raise RuntimeError("mất kết nối")

        ket_qua = await _Hong().run(unit_code="VOP397", so_dien_thoai="0912345678")

        assert not ket_qua.ok
        assert "Chưa lưu được" in ket_qua.error
