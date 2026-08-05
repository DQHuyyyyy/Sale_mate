"""Test InventoryDB — dùng SQLite in-memory, không gọi Postgres thật (đúng
quy ước dự án: không test nào được gọi DB/API ngoài thật)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from src.data.sources.inventory import InventoryUnit
from src.data.stores.inventory_db import InventoryDB

_UNITS = [
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
        photos=["a.jpg", "b.jpg"],
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


@pytest.fixture
def db() -> InventoryDB:
    engine = create_engine("sqlite:///:memory:")
    return InventoryDB("sqlite:///:memory:", engine=engine)


def test_upsert_va_query_khong_dieu_kien_tra_het(db: InventoryDB):
    count = db.upsert_units(_UNITS)

    assert count == 2
    assert len(db.query_units()) == 2


def test_query_theo_unit_code_khong_phan_biet_hoa_thuong(db: InventoryDB):
    db.upsert_units(_UNITS)

    rows = db.query_units(unit_code="vop001")

    assert len(rows) == 1
    assert rows[0]["price_label"] == "3,5 tỷ"
    assert rows[0]["photos"] == ["a.jpg", "b.jpg"]


def test_query_theo_toa(db: InventoryDB):
    db.upsert_units(_UNITS)

    rows = db.query_units(building="R103")

    assert len(rows) == 2


def test_query_theo_loai_can_khop_gan_dung(db: InventoryDB):
    db.upsert_units(_UNITS)

    rows = db.query_units(unit_type="3PN")

    assert [r["unit_code"] for r in rows] == ["VOP002"]


def test_upsert_lai_cung_ma_can_thi_ghi_de_khong_trung(db: InventoryDB):
    db.upsert_units(_UNITS)

    updated = InventoryUnit(
        unit_code="VOP001",
        building="R103",
        floor="12",
        room_no="1201",
        unit_type="2PN, 1WC",
        area_m2="60m2",
        direction="Đông Nam",
        view="View hồ",
        legal_status="Sẵn sổ",
        price_label="3,8 tỷ",  # gia doi
        furniture="Full nội thất",
        status="reserved",  # tinh trang doi
    )
    db.upsert_units([updated])

    rows = db.query_units(unit_code="VOP001")
    assert len(rows) == 1
    assert rows[0]["price_label"] == "3,8 tỷ"
    assert rows[0]["status"] == "reserved"
    assert len(db.query_units()) == 2  # khong sinh du thua dong


def test_khong_khop_dieu_kien_tra_danh_sach_rong(db: InventoryDB):
    db.upsert_units(_UNITS)

    assert db.query_units(unit_code="khong-ton-tai") == []


def test_upsert_danh_sach_rong_khong_lam_gi(db: InventoryDB):
    assert db.upsert_units([]) == 0
    assert db.query_units() == []
