"""Test registry và tool tồn kho (query InventoryDB thật qua SQLite in-memory,
không phải mock cứng — chỉ không gọi Postgres thật đúng quy ước dự án)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools import registry
from src.agents.tools.inventory import InventoryLookupTool
from src.data.sources.inventory import InventoryUnit
from src.data.stores.inventory_db import InventoryDB

_FAKE_UNITS = [
    InventoryUnit(
        unit_code="VOP001",
        building="R103",
        floor="12",
        room_no="1201",
        unit_type="2PN, 1WC",
        area_m2="60m2",
        direction="Đông Nam",
        view="View hồ",
        legal_status="Sẵn sổ",
        price_label="3,5 tỷ",
        furniture="Full nội thất",
        status="available",
    ),
    InventoryUnit(
        unit_code="VOP002",
        building="R103",
        floor="20",
        room_no="2001",
        unit_type="3PN, 2WC",
        area_m2="90m2",
        direction="Tây Bắc",
        view="View nội khu",
        legal_status="Sẵn sổ",
        price_label="5,2 tỷ",
        furniture="Cơ bản",
        status="sold",
    ),
]


@pytest.fixture(autouse=True)
def _fake_inventory_db(monkeypatch):
    """SQLite in-memory nạp sẵn 2 căn — không gọi Postgres thật.

    `run()` gọi query qua `asyncio.to_thread` (thread khác thread tạo engine)
    — SQLite `:memory:` mặc định chỉ tồn tại trong đúng connection tạo ra nó,
    nên bắt buộc `StaticPool` để giữ một connection dùng chung xuyên thread.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = InventoryDB("sqlite:///:memory:", engine=engine)
    db.upsert_units(_FAKE_UNITS)
    monkeypatch.setattr("src.agents.tools.inventory.get_inventory_db", lambda: db)


def test_tool_tu_dang_ky_vao_registry():
    assert registry.get("inventory_lookup") is not None


def test_registry_khong_cho_trung_ten():
    with pytest.raises(ValueError, match="trùng tên"):
        registry.add(InventoryLookupTool())


def test_spec_co_du_thong_tin_cho_llm():
    spec = registry.get("inventory_lookup").spec()

    assert spec["function"]["name"] == "inventory_lookup"
    assert "unit_code" in spec["function"]["parameters"]["properties"]
    assert "building" in spec["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tra_ton_kho_theo_toa():
    result = await InventoryLookupTool().run(building="R103")

    assert result.ok
    assert len(result.data) == 2
    assert result.source == "inventory:postgres"


@pytest.mark.asyncio
async def test_tra_dung_1_can_theo_ma_can():
    result = await InventoryLookupTool().run(unit_code="vop001")  # khong phan biet hoa/thuong

    assert result.ok
    assert len(result.data) == 1
    assert result.data[0]["status_label"] == "Còn"
    # Gia/tinh trang la du lieu dong that, khong duoc bia
    assert result.data[0]["price_label"] == "3,5 tỷ"


@pytest.mark.asyncio
async def test_tra_ton_kho_loc_theo_loai_can():
    result = await InventoryLookupTool().run(unit_type="3PN")

    assert [row["unit_code"] for row in result.data] == ["VOP002"]
    assert result.data[0]["status_label"] == "Đã bán"


@pytest.mark.asyncio
async def test_khong_khop_thi_tra_rong_chu_khong_no():
    result = await InventoryLookupTool().run(unit_code="khong-ton-tai")

    assert result.ok
    assert result.data == []
    assert result.error


@pytest.mark.asyncio
async def test_tham_so_sai_thi_tra_failure_khong_raise():
    """Tool không bao giờ ném lỗi ra ngoài — agent tự quyết định xử lý."""
    result = await InventoryLookupTool().run(unit_code=123)  # sai kieu du lieu

    assert result.ok is False
    assert "không hợp lệ" in result.error


@pytest.mark.asyncio
async def test_loi_ket_noi_db_thi_tra_failure_ro_rang(monkeypatch):
    class _BrokenDB:
        def query_units(self, **kwargs):
            raise ConnectionError("không kết nối được")

    monkeypatch.setattr("src.agents.tools.inventory.get_inventory_db", lambda: _BrokenDB())

    result = await InventoryLookupTool().run()

    assert result.ok is False
    assert "không truy vấn được" in result.error.lower()
