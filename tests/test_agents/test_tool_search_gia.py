"""Test lọc theo giá / diện tích / sắp xếp của `inventory_search`.

Tách khỏi test_tool_search.py vì cần dữ liệu có CỘT SỐ (`price_value`,
`area_value`) — `upsert_units` không ghi hai cột đó nên phải chèn thẳng.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools.search import InventorySearchTool, extract_criteria, vocabulary
from src.data.stores.inventory_db import InventoryDB, inventory_units_table, metadata


def _row(code, price, area, status="available", building="S210", unit_type="2PN, 1WC"):
    return {
        "unit_code": code,
        "building": building,
        "floor": "10",
        "room_no": "1001",
        "unit_type": unit_type,
        "area_m2": f"{area}m2",
        "direction": "Đông Nam",
        "view": "View hồ",
        "legal_status": "Sẵn sổ",
        "price_label": f"{price} tỷ",
        "furniture": "Cơ bản",
        "status": status,
        "photos": [],
        "price_value": price,
        "area_value": area,
    }


_ROWS = [
    _row("VOP001", 2.0, 31),
    _row("VOP002", 2.5, 45),
    _row("VOP003", 3.0, 60),  # ĐÚNG biên 3 tỷ
    _row("VOP004", 4.5, 90),
    _row("VOP005", 1.8, 28, status="sold"),  # đã bán, không được lọt
    {**_row("VOP006", 0, 0), "price_value": None, "area_value": None},  # không rõ số
]


@pytest.fixture(autouse=True)
def _kho(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine, tables=[inventory_units_table])
    with engine.begin() as conn:
        conn.execute(inventory_units_table.insert(), _ROWS)

    db = InventoryDB("sqlite:///:memory:", engine=engine)
    monkeypatch.setattr("src.agents.tools.search.get_inventory_db", lambda: db)
    vocabulary.clear()
    yield
    vocabulary.clear()


# ---------- Rút khoảng giá từ câu hỏi ----------


@pytest.mark.parametrize(
    ("query", "mong_doi"),
    [
        ("tìm các căn hộ có tầm giá dưới 3 tỷ", {"price_max": 3.0}),
        ("căn không quá 2,5 tỷ", {"price_max": 2.5}),
        ("tìm căn trên 5 tỷ", {"price_min": 5.0}),
        ("căn từ 2 đến 3 tỷ", {"price_min": 2.0, "price_max": 3.0}),
        ("căn 2-4 tỷ", {"price_min": 2.0, "price_max": 4.0}),
    ],
)
def test_rut_dung_khoang_gia(query, mong_doi):
    ket_qua = extract_criteria(query)

    for khoa, gia_tri in mong_doi.items():
        assert ket_qua[khoa] == gia_tri


def test_dau_phay_la_dau_thap_phan_tieng_viet():
    """'2,5 tỷ' là 2.5 chứ không phải 25."""
    assert extract_criteria("căn dưới 2,5 tỷ")["price_max"] == 2.5


def test_re_nhat_thi_sap_xep_tang_dan():
    ket_qua = extract_criteria("căn rẻ nhất còn hàng")

    assert ket_qua["sort"] == "gia_tang"
    assert ket_qua["limit"] == 3


# ---------- Lọc thật ----------


@pytest.mark.asyncio
async def test_duoi_3_ty_bao_gom_ca_can_dung_3_ty():
    """Biên tính cả — khớp bộ lọc 'Từ – Đến' trên portal, hai chỗ phải ra cùng số."""
    ket_qua = await InventorySearchTool().run(price_max=3)

    ma = {r["unit_code"] for r in ket_qua.data["danh_sach"]}
    assert ma == {"VOP001", "VOP002", "VOP003"}


@pytest.mark.asyncio
async def test_can_da_ban_khong_lot_vao_ket_qua():
    ket_qua = await InventorySearchTool().run(price_max=2)

    assert "VOP005" not in {r["unit_code"] for r in ket_qua.data["danh_sach"]}


@pytest.mark.asyncio
async def test_can_khong_ro_gia_bi_loai_chu_khong_coi_la_0():
    """Coi None là 0 thì căn thiếu giá lọt vào MỌI câu hỏi 'dưới X tỷ'."""
    ket_qua = await InventorySearchTool().run(price_max=3)

    assert "VOP006" not in {r["unit_code"] for r in ket_qua.data["danh_sach"]}


@pytest.mark.asyncio
async def test_khoang_hai_dau():
    ket_qua = await InventorySearchTool().run(price_min=2.5, price_max=4.5)

    assert {r["unit_code"] for r in ket_qua.data["danh_sach"]} == {"VOP002", "VOP003", "VOP004"}


@pytest.mark.asyncio
async def test_loc_theo_dien_tich():
    ket_qua = await InventorySearchTool().run(area_min=50)

    assert {r["unit_code"] for r in ket_qua.data["danh_sach"]} == {"VOP003", "VOP004"}


# ---------- Sắp xếp và giới hạn ----------


@pytest.mark.asyncio
async def test_sap_xep_gia_tang_dan():
    ket_qua = await InventorySearchTool().run(sort="gia_tang")

    ma = [r["unit_code"] for r in ket_qua.data["danh_sach"]]
    assert ma[:3] == ["VOP001", "VOP002", "VOP003"]


@pytest.mark.asyncio
async def test_can_thieu_gia_xuong_cuoi_khong_len_dau():
    ket_qua = await InventorySearchTool().run(sort="gia_tang")

    ma = [r["unit_code"] for r in ket_qua.data["danh_sach"]]
    assert ma[-1] == "VOP006"


@pytest.mark.asyncio
async def test_limit_cat_bot_nhung_van_bao_tong_so():
    ket_qua = await InventorySearchTool().run(sort="gia_tang", limit=2)

    assert len(ket_qua.data["danh_sach"]) == 2
    # Tong so khop van la con so THAT, khong phai so da cat
    assert ket_qua.data["tong_so_khop"] == 5
