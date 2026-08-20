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


class TestKhongTuTaoBangTrenPostgres:
    """Sự cố thật 19/08/2026: `ensure_table()` chạy ở đầu MỌI thao tác và đã
    lặng lẽ tạo `dat_coc_lead` trên database thật TRƯỚC khi ai chạy migration
    009. `CREATE TABLE IF NOT EXISTS` của 009 sau đó thấy bảng đã có nên bỏ qua.

    Bảng SQLAlchemy dựng ra thiếu DEFAULT, thiếu CHECK, thiếu unique index và
    **thiếu RLS** — bảng chứa tên với số điện thoại khách thật nằm mở cho role
    `anon`. Migration mới là nguồn sự thật của schema trên Postgres.
    """

    def test_postgres_thi_khong_dung_toi_engine(self) -> None:
        """Engine Postgres giả, không có server nào ở đầu kia. Hàm mà thật sự
        chạy `create_all` thì nó phải kết nối, và test này sẽ nổ."""
        from sqlalchemy import create_engine

        from src.data.stores.dat_coc_db import DatCocDB

        db = DatCocDB("", engine=create_engine("postgresql://khong-co-that:5432/x"))

        db.ensure_table()  # không được raise, và không được kết nối

    def test_sqlite_van_tao_bang(self) -> None:
        """Test dùng SQLite in-memory, ở đó không migration nào chạy."""
        from sqlalchemy import create_engine, inspect

        from src.data.stores.dat_coc_db import DatCocDB

        engine = create_engine("sqlite:///:memory:")
        DatCocDB("", engine=engine).ensure_table()

        assert inspect(engine).has_table("dat_coc_lead")

    def test_hai_cot_hay_bi_bo_qua_co_server_default(self) -> None:
        """`default=` của SQLAlchemy là mặc định phía PYTHON, không sinh ra
        DEFAULT trong DDL — INSERT bằng SQL thuần vẫn ăn NotNullViolation."""
        from src.data.stores.dat_coc_db import dat_coc_lead_table

        for ten in ("trang_thai", "created_at"):
            assert dat_coc_lead_table.c[ten].server_default is not None


def test_moi_module_goi_inventory_deu_duoc_va_trong_conftest() -> None:
    """Chốt chặn cho một lỗi đã xảy ra HAI lần.

    `get_inventory_db()` đọc `get_settings()` toàn cục, tức `.env`, tức Supabase
    production. `tests/conftest.py` vá nó bằng SQLite rỗng — nhưng vá theo TÊN
    MODULE, nên module mới nào gọi hàm này mà quên thêm vào danh sách thì test
    của nó đọc thẳng dữ liệu thật, xanh hay đỏ tuỳ hôm đó production có gì.

    Lần gần nhất: `dat_coc` thêm phép kiểm tình trạng căn, quên vá, và hai test
    xanh suốt chỉ vì VOP397 tình cờ đang "Còn". Chúng đỏ đúng lúc căn đó chuyển
    sang "Đã đặt cọc" — nghĩa là chúng chưa bao giờ chạy độc lập.
    """
    import pathlib
    import re

    goc = pathlib.Path(__file__).resolve().parents[2]
    goi_ham = {
        f"src.agents.tools.{f.stem}"
        for f in (goc / "src" / "agents" / "tools").glob("*.py")
        if "get_inventory_db" in f.read_text(encoding="utf-8")
    }
    da_va = set(re.findall(r'"(src\.agents\.tools\.\w+)"', (goc / "tests" / "conftest.py").read_text(encoding="utf-8")))

    thieu = goi_ham - da_va
    assert not thieu, f"Module gọi get_inventory_db nhưng chưa vá trong conftest: {sorted(thieu)}"
