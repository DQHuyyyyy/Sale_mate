"""Test tool so sánh nhiều căn.

Lỗi đã xảy ra thật trên production: bấm gợi ý "Có thể so sánh căn VOP619 với căn
VOP893 không?" thì trợ lý trả "chưa đủ dữ liệu". `inventory_lookup._extract_args`
dùng `re.search` nên chỉ bắt mã ĐẦU TIÊN — VOP893 không bao giờ được tra, model
thiếu một vế và từ chối.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools import so_sanh as mod_so_sanh
from src.agents.tools.inventory import _extract_args as _args_mot_can
from src.agents.tools.so_sanh import TOI_DA_CAN, SoSanhCanTool, _rut_tham_so
from src.data.sources.inventory import InventoryUnit
from src.data.stores.inventory_db import InventoryDB


def _can(ma: str, gia: str) -> InventoryUnit:
    return InventoryUnit(
        unit_code=ma,
        building="S210",
        floor="11",
        room_no="1101",
        unit_type="2PN, 2WC",
        area_m2="55",
        direction="Đông Nam",
        view="Bể bơi",
        legal_status="Sẵn sổ",
        price_label=gia,
        furniture="Full nội thất",
        status="available",
        photos=[],
    )


@pytest.fixture(autouse=True)
def kho_co_du_lieu(monkeypatch):
    """Tồn kho SQLite có sẵn ba căn — đè fixture rỗng ở conftest."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = InventoryDB("sqlite:///:memory:", engine=engine)
    db.ensure_table()
    db.upsert_units([_can("VOP619", "3,850 tỷ"), _can("VOP893", "2,900 tỷ"), _can("VOP758", "2,750 tỷ")])
    monkeypatch.setattr("src.agents.tools.so_sanh.get_inventory_db", lambda: db)
    return db


class TestNhanCau:
    def test_hai_ma_can_thi_nhan(self) -> None:
        args = _rut_tham_so("Có thể so sánh căn VOP619 với căn VOP893 không?")

        assert args == {"unit_codes": ["VOP619", "VOP893"], "bo_bot": 0}

    def test_khong_doi_phai_co_chu_so_sanh(self) -> None:
        """ "VOP619 và VOP893 cái nào tốt hơn" không có chữ 'so sánh' nào."""
        assert _rut_tham_so("VOP619 và VOP893 cái nào tốt hơn") is not None

    def test_mot_ma_can_thi_nhuong_inventory_lookup(self) -> None:
        assert _rut_tham_so("căn VOP619 giá bao nhiêu") is None

    def test_ma_trung_lap_khong_tinh_la_hai_can(self) -> None:
        assert _rut_tham_so("căn VOP619, nhắc lại VOP619 nhé") is None

    def test_inventory_lookup_nhuong_khi_co_nhieu_ma(self) -> None:
        """Hai tool cùng chạy thì prompt có thêm một bản sao vô nghĩa của căn đầu."""
        assert _args_mot_can("so sánh VOP619 với VOP893") is None
        assert _args_mot_can("căn VOP619 còn không") == {"unit_code": "VOP619"}


class TestChay:
    @pytest.mark.asyncio
    async def test_lay_du_ca_hai_can(self) -> None:
        """Chốt chặn chính — đây là thứ bản cũ làm sai."""
        ket_qua = await SoSanhCanTool().run(unit_codes=["VOP619", "VOP893"])

        assert ket_qua.ok
        assert ket_qua.data["so_can"] == 2
        assert [c["unit_code"] for c in ket_qua.data["can"]] == ["VOP619", "VOP893"]
        assert "khong_tim_thay" not in ket_qua.data

    @pytest.mark.asyncio
    async def test_giu_dung_thu_tu_nguoi_dung_hoi(self) -> None:
        ket_qua = await SoSanhCanTool().run(unit_codes=["VOP893", "VOP619"])

        assert [c["unit_code"] for c in ket_qua.data["can"]] == ["VOP893", "VOP619"]

    @pytest.mark.asyncio
    async def test_noi_ro_can_khong_ton_tai(self) -> None:
        """Im lặng bỏ qua là để model so sánh hai căn rồi lờ căn thứ ba đi."""
        ket_qua = await SoSanhCanTool().run(unit_codes=["VOP619", "VOP000"])

        assert ket_qua.data["khong_tim_thay"] == ["VOP000"]
        assert "VOP000" in ket_qua.data["luu_y"]

    @pytest.mark.asyncio
    async def test_khong_phan_biet_hoa_thuong(self) -> None:
        ket_qua = await SoSanhCanTool().run(unit_codes=["vop619", "vop893"])

        assert ket_qua.data["so_can"] == 2

    @pytest.mark.asyncio
    async def test_vuot_tran_thi_cat_va_noi_ro(self) -> None:
        ma = [f"VOP{i:03d}" for i in range(1, 8)]
        args = _rut_tham_so("so sánh " + " ".join(ma))

        assert len(args["unit_codes"]) == TOI_DA_CAN
        assert args["bo_bot"] == len(ma) - TOI_DA_CAN

        ket_qua = await SoSanhCanTool().run(**args)
        assert ket_qua.data["bo_bot"] == args["bo_bot"]
        assert "luu_y_tran" in ket_qua.data

    @pytest.mark.asyncio
    async def test_mot_ma_thi_bao_loi_chu_khong_raise(self) -> None:
        ket_qua = await SoSanhCanTool().run(unit_codes=["VOP619"])

        assert not ket_qua.ok
        assert "hai mã căn" in ket_qua.error

    @pytest.mark.asyncio
    async def test_db_hong_thi_tra_failure(self, monkeypatch) -> None:
        """Tool không raise — một tool hỏng không làm đứt cả lượt trả lời."""

        class _Hong:
            def query_units(self, **_: object):
                raise RuntimeError("mất kết nối")

        monkeypatch.setattr(mod_so_sanh, "get_inventory_db", lambda: _Hong())

        ket_qua = await SoSanhCanTool().run(unit_codes=["VOP619", "VOP893"])

        assert not ket_qua.ok
        assert "Không truy vấn được" in ket_qua.error
