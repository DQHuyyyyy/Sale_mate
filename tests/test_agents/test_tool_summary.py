"""Test tool thống kê tồn kho — trả lời câu hỏi về SỐ LƯỢNG.

Dùng SQLite in-memory nạp sẵn vài căn, không gọi Postgres thật (quy ước dự án).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools.summary import InventorySummaryTool, _extract_args
from src.data.sources.inventory import InventoryUnit
from src.data.stores.inventory_db import InventoryDB


def _can(ma: str, toa: str, loai: str, trang_thai: str) -> InventoryUnit:
    return InventoryUnit(
        unit_code=ma,
        building=toa,
        floor="10",
        room_no="1001",
        unit_type=loai,
        area_m2="50m2",
        direction="Đông Nam",
        view="View hồ",
        legal_status="Sẵn sổ",
        price_label="3 tỷ",
        furniture="Cơ bản",
        status=trang_thai,
    )


_KHO = [
    _can("VOP001", "S210", "2PN, 1WC", "available"),
    _can("VOP002", "S210", "2PN, 1WC", "available"),
    _can("VOP003", "S210", "Studio", "sold"),
    _can("VOP004", "R103", "Studio", "available"),
    _can("VOP005", "R103", "3PN, 2WC", "sold"),
]


@pytest.fixture(autouse=True)
def _kho_gia(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = InventoryDB("sqlite:///:memory:", engine=engine)
    db.upsert_units(_KHO)
    monkeypatch.setattr("src.agents.tools.summary.get_inventory_db", lambda: db)


# ---------- Khi nào tool chạy ----------


@pytest.mark.parametrize(
    "query",
    [
        "còn bao nhiêu căn chưa được bán",
        "Toà S210 còn mấy căn?",
        "thống kê tồn kho giúp tôi",
        "đã bán bao nhiêu căn rồi",
    ],
)
def test_cau_hoi_so_luong_thi_tool_chay(query):
    assert _extract_args(query) == {}


@pytest.mark.parametrize(
    "query",
    [
        "giá căn VOP345 bao nhiêu",  # co ma can -> viec cua inventory_lookup
        "tìm căn 2 phòng ngủ view biển",  # tim theo tieu chi -> inventory_search
        "thủ tục sang tên sổ đỏ",
        "xin chào",
    ],
)
def test_cau_hoi_khac_thi_tool_im_lang(query):
    assert _extract_args(query) is None


def test_co_ma_can_thi_khong_dem_ca_kho():
    """'Còn bao nhiêu căn giống VOP345' vẫn là hỏi về một căn cụ thể."""
    assert _extract_args("còn bao nhiêu căn như VOP345") is None


# ---------- Kết quả thống kê ----------


@pytest.mark.asyncio
async def test_dem_dung_con_trong_va_da_ban():
    ket_qua = await InventorySummaryTool().run()

    assert ket_qua.ok
    assert ket_qua.data["tong_so_can"] == 5
    assert ket_qua.data["con_trong"] == 3
    assert ket_qua.data["da_ban"] == 2


@pytest.mark.asyncio
async def test_chi_thong_ke_can_con_trong_theo_toa():
    """Sale cần biết còn gì để chào khách, không cần phân bố của căn đã bán."""
    ket_qua = await InventorySummaryTool().run()

    assert ket_qua.data["con_trong_theo_toa"] == {"R103": 1, "S210": 2}


@pytest.mark.asyncio
async def test_loc_theo_toa():
    ket_qua = await InventorySummaryTool().run(building="S210")

    assert ket_qua.data["tong_so_can"] == 3
    assert ket_qua.data["con_trong"] == 2


@pytest.mark.asyncio
async def test_khong_khop_thi_bao_ro_chu_khong_no():
    ket_qua = await InventorySummaryTool().run(building="KHONG-CO")

    assert ket_qua.ok
    assert ket_qua.data == {}
    assert ket_qua.error


@pytest.mark.asyncio
async def test_db_hong_thi_tra_failure_khong_raise(monkeypatch):
    class _Hong:
        def query_units(self, **kwargs):
            raise ConnectionError("mất kết nối")

    monkeypatch.setattr("src.agents.tools.summary.get_inventory_db", lambda: _Hong())

    ket_qua = await InventorySummaryTool().run()

    assert ket_qua.ok is False
    assert "không truy vấn được" in ket_qua.error.lower()
