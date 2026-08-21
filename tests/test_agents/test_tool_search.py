"""Test tool tìm căn theo tiêu chí.

Từ vựng lọc phải đọc từ dữ liệu, không từ danh sách viết cứng — nên fixture ở
đây nạp một bộ căn có kiểu ghi KHÔNG thống nhất ('2 PN, 1WC' lẫn '2PN, 2WC') để
bắt đúng lỗi mà cách hardcode '%2PN%' sẽ mắc phải.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools.search import InventorySearchTool, extract_criteria, vocabulary
from src.data.sources.inventory import InventoryUnit
from src.data.stores.inventory_db import InventoryDB


def _unit(code, building, unit_type, view, direction="Đông Nam", status="available", price="3 tỷ"):
    return InventoryUnit(
        unit_code=code,
        building=building,
        floor="10",
        room_no="1001",
        unit_type=unit_type,
        area_m2="60m2",
        direction=direction,
        view=view,
        legal_status="Sẵn sổ",
        price_label=price,
        furniture="Cơ bản",
        status=status,
    )


_UNITS = [
    _unit("VOP001", "S210", "2 PN, 1WC", "View biển hồ"),  # co dau cach
    _unit("VOP002", "S210", "2PN, 2WC", "View biển đẹp"),  # khong dau cach
    _unit("VOP003", "R103", "Studio", "View nội khu"),
    _unit("VOP004", "S1", "1PN, 1WC", "View hồ", direction="Tây Bắc"),
    _unit("VOP005", "S210", "2PN, 1WC", "View biển", status="sold"),
]


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = InventoryDB("sqlite:///:memory:", engine=engine)
    db.upsert_units(_UNITS)
    monkeypatch.setattr("src.agents.tools.search.get_inventory_db", lambda: db)
    vocabulary.clear()  # tu vung nho tam giua cac test
    yield
    vocabulary.clear()


# ---------- Trích tiêu chí ----------


def test_so_phong_ngu_khop_ca_hai_kieu_ghi():
    """Điểm mấu chốt: '2 PN, 1WC' và '2PN, 2WC' phải cùng khớp khi hỏi 2 phòng ngủ."""
    assert extract_criteria("tìm căn 2 phòng ngủ")["unit_type"] == "2PN"


def test_loai_can_mot_bien_the_thi_tra_dung_gia_tri_trong_db():
    """Chỉ một loại bắt đầu bằng 1PN ⇒ trả nguyên văn giá trị thật, không tự chế."""
    assert extract_criteria("tìm căn 1PN")["unit_type"] == "1PN, 1WC"


def test_studio_khop_theo_ten_goi():
    assert extract_criteria("còn căn studio nào không")["unit_type"] == "Studio"


def test_toa_khop_theo_tu_rieng_khong_phai_chuoi_con():
    """'S210' không được hiểu thành toà 'S1' hay 'S2' nằm lọt bên trong."""
    assert extract_criteria("căn ở tòa S210")["building"] == "S210"


def test_khong_bat_nham_toa_khi_ma_toa_nam_giua_tu_khac():
    """Toà 'S1' tồn tại, nhưng 'S1' không xuất hiện như một từ riêng ở đây."""
    assert (extract_criteria("tìm căn 2 phòng ngủ") or {}).get("building") is None


def test_huong_nhieu_tu_van_khop():
    assert extract_criteria("tìm căn hướng Đông Nam")["direction"] == "Đông Nam"


def test_view_chi_lay_mot_tu():
    """Lấy hai từ thì 'view hồ tòa R103' ra từ khoá 'hồ tòa' và không khớp gì."""
    criteria = extract_criteria("tìm căn 1PN view hồ tòa R103")

    assert criteria["view_keyword"] == "hồ"
    assert criteria["building"] == "R103"


def test_co_ma_can_thi_nhuong_cho_tool_tra_theo_ma():
    assert extract_criteria("thông tin căn VOP345") is None


def test_khong_co_tieu_chi_nao_thi_im_lang():
    assert extract_criteria("xin chào") is None


def test_tu_vung_doc_tu_du_lieu_khong_phai_hardcode():
    values = vocabulary.get()

    assert set(values["building"]) == {"S210", "R103", "S1"}
    assert "2 PN, 1WC" in values["unit_type"]


# ---------- Tìm kiếm ----------


@pytest.mark.asyncio
async def test_tim_2pn_view_bien_khop_ca_hai_kieu_ghi():
    result = await InventorySearchTool().run(unit_type="2PN", view_keyword="biển")

    assert result.ok
    codes = [r["unit_code"] for r in result.data["can_hien_thi"]]
    assert codes == ["VOP001", "VOP002"]  # '2 PN, 1WC' lan '2PN, 2WC'
    assert result.source == "inventory:postgres"


@pytest.mark.asyncio
async def test_khong_bao_gio_chao_can_da_ban():
    """VOP005 khớp mọi tiêu chí nhưng status='sold' ⇒ phải bị loại."""
    result = await InventorySearchTool().run(unit_type="2PN")

    assert "VOP005" not in [r["unit_code"] for r in result.data["can_hien_thi"]]


@pytest.mark.asyncio
async def test_loc_theo_huong():
    result = await InventorySearchTool().run(direction="Tây Bắc")

    assert [r["unit_code"] for r in result.data["can_hien_thi"]] == ["VOP004"]


@pytest.mark.asyncio
async def test_khong_khop_thi_tra_rong_kem_ly_do():
    result = await InventorySearchTool().run(unit_type="Studio", view_keyword="biển")

    assert result.ok
    assert result.data == []
    assert "Không có căn nào" in result.error


@pytest.mark.asyncio
async def test_bao_tong_so_khop_de_khong_noi_nham_la_tat_ca():
    result = await InventorySearchTool().run(building="S210")

    assert result.data["tong_so_khop"] == 2  # VOP005 da ban nen khong tinh


@pytest.mark.asyncio
async def test_gioi_han_so_can_dua_vao_prompt(monkeypatch):
    monkeypatch.setattr("src.agents.tools.search.MAX_RESULTS", 1)

    result = await InventorySearchTool().run(unit_type="2PN")

    assert result.data["tong_so_khop"] == 2
    assert len(result.data["can_hien_thi"]) == 1


@pytest.mark.asyncio
async def test_loi_db_thi_tra_failure_khong_raise(monkeypatch):
    class _Broken:
        def query_units(self, **kwargs):
            raise ConnectionError("mất kết nối")

    monkeypatch.setattr("src.agents.tools.search.get_inventory_db", lambda: _Broken())

    result = await InventorySearchTool().run(unit_type="2PN")

    assert result.ok is False
    assert "không truy vấn được" in result.error.lower()
