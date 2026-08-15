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


def _row(code, price, area, status="available", building="S210", unit_type="2PN, 1WC", subdivision="Ocean Park 1"):
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
        "subdivision": subdivision,
    }


_ROWS = [
    _row("VOP001", 2.0, 31),
    _row("VOP002", 2.5, 45, subdivision="Ocean Park 2"),
    _row("VOP003", 3.0, 60),  # ĐÚNG biên 3 tỷ
    _row("VOP004", 4.5, 90, subdivision="Ocean Park 2"),
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
async def test_khong_qua_3_ty_bao_gom_ca_can_dung_3_ty():
    """Không có cờ nghiêm ngặt thì biên tính cả — đúng nghĩa "không quá 3 tỷ"."""
    ket_qua = await InventorySearchTool().run(price_max=3)

    ma = {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}
    assert ma == {"VOP001", "VOP002", "VOP003"}


@pytest.mark.asyncio
async def test_duoi_3_ty_loai_can_dung_3_ty():
    """ "Dưới" là nghiêm ngặt. Kho thật có 4 căn giá đúng 3 tỷ nên người dùng
    đếm được sự khác nhau giữa "dưới 3 tỷ" và "không quá 3 tỷ"."""
    ket_qua = await InventorySearchTool().run(price_max=3, price_max_nghiem_ngat=True)

    ma = {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}
    assert "VOP003" not in ma  # VOP003 giá đúng 3 tỷ
    assert ma == {"VOP001", "VOP002"}


@pytest.mark.asyncio
async def test_tren_2_ty_loai_can_dung_2_ty():
    ket_qua = await InventorySearchTool().run(price_min=2, price_min_nghiem_ngat=True)

    ma = {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}
    assert "VOP001" not in ma  # VOP001 giá đúng 2 tỷ
    assert ma == {"VOP002", "VOP003", "VOP004"}


@pytest.mark.asyncio
async def test_limit_qua_lon_khong_lam_hong_tool():
    """Model hay xin `limit: 100` cho câu "liệt kê hết". Trần ở schema biến việc
    đó thành lỗi validation và agent mất luôn dữ liệu."""
    ket_qua = await InventorySearchTool().run(price_max=3, limit=100)

    assert ket_qua.ok
    assert ket_qua.data["tong_so_khop"] == 3


@pytest.mark.asyncio
async def test_cat_bot_danh_sach_thi_phai_noi_ro_tong_that():
    """Model đọc `tong_so_khop`=25 và `danh_sach` 8 phần tử vẫn trả lời "8 căn" —
    nó đếm dòng. Một câu tiếng Việt ngay trong dữ liệu chặn được lỗi đó."""
    ket_qua = await InventorySearchTool().run(limit=1)

    if ket_qua.data["tong_so_khop"] > len(ket_qua.data["can_hien_thi"]):
        assert str(ket_qua.data["tong_so_khop"]) in ket_qua.data["ghi_chu"]
        assert "đừng đếm" in ket_qua.data["ghi_chu"]


@pytest.mark.asyncio
async def test_can_da_ban_khong_lot_vao_ket_qua():
    ket_qua = await InventorySearchTool().run(price_max=2)

    assert "VOP005" not in {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}


@pytest.mark.asyncio
async def test_can_khong_ro_gia_bi_loai_chu_khong_coi_la_0():
    """Coi None là 0 thì căn thiếu giá lọt vào MỌI câu hỏi 'dưới X tỷ'."""
    ket_qua = await InventorySearchTool().run(price_max=3)

    assert "VOP006" not in {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}


@pytest.mark.asyncio
async def test_khoang_hai_dau():
    ket_qua = await InventorySearchTool().run(price_min=2.5, price_max=4.5)

    assert {r["unit_code"] for r in ket_qua.data["can_hien_thi"]} == {"VOP002", "VOP003", "VOP004"}


@pytest.mark.asyncio
async def test_loc_theo_dien_tich():
    ket_qua = await InventorySearchTool().run(area_min=50)

    assert {r["unit_code"] for r in ket_qua.data["can_hien_thi"]} == {"VOP003", "VOP004"}


# ---------- Sắp xếp và giới hạn ----------


@pytest.mark.asyncio
async def test_sap_xep_gia_tang_dan():
    ket_qua = await InventorySearchTool().run(sort="gia_tang")

    ma = [r["unit_code"] for r in ket_qua.data["can_hien_thi"]]
    assert ma[:3] == ["VOP001", "VOP002", "VOP003"]


@pytest.mark.asyncio
async def test_can_thieu_gia_xuong_cuoi_khong_len_dau():
    ket_qua = await InventorySearchTool().run(sort="gia_tang")

    ma = [r["unit_code"] for r in ket_qua.data["can_hien_thi"]]
    assert ma[-1] == "VOP006"


@pytest.mark.asyncio
async def test_limit_cat_bot_nhung_van_bao_tong_so():
    ket_qua = await InventorySearchTool().run(sort="gia_tang", limit=2)

    assert len(ket_qua.data["can_hien_thi"]) == 2
    # Tong so khop van la con so THAT, khong phai so da cat
    assert ket_qua.data["tong_so_khop"] == 5


# ---------- Người dùng ghi số thay vì "tỷ" ----------


@pytest.mark.parametrize(
    ("query", "mong_doi"),
    [
        ("có bao nhiêu căn hộ trên 5.000.000.000", {"price_min": 5.0}),
        ("trên 5000000000", {"price_min": 5.0}),
        ("dưới 500 triệu", {"price_max": 0.5}),
        ("từ 2.000.000.000 đến 3.000.000.000", {"price_min": 2.0, "price_max": 3.0}),
        ("căn dưới 3", {"price_max": 3.0}),  # khong don vi, so nho -> ty
        ("căn dưới 3 tỷ", {"price_max": 3.0}),
    ],
)
def test_doc_duoc_moi_cach_ghi_gia(query, mong_doi):
    """Người dùng gõ '5.000.000.000' hay '5 tỷ' đều phải ra cùng một kết quả."""
    ket_qua = extract_criteria(query)

    for khoa, gia_tri in mong_doi.items():
        assert ket_qua[khoa] == gia_tri


def test_dau_cham_la_dau_ngan_nghin_dau_phay_la_thap_phan():
    """Quy ước Việt Nam, và cột giá trong DB cũng ghi kiểu này ('2,120 tỷ')."""
    assert extract_criteria("dưới 2,5 tỷ")["price_max"] == 2.5
    assert extract_criteria("dưới 2.500.000.000")["price_max"] == 2.5


# ---------- Nghĩa của câu hỏi: "dưới" vs "không quá" vs "khoảng" ----------


@pytest.mark.parametrize(
    ("query", "mong_doi"),
    [
        # "dưới/trên" là nghiêm ngặt, "không quá/từ" tính cả biên.
        ("căn dưới 3 tỷ", {"price_max": 3.0, "price_max_nghiem_ngat": True}),
        ("căn không quá 3 tỷ", {"price_max": 3.0}),
        ("căn trên 3 tỷ", {"price_min": 3.0, "price_min_nghiem_ngat": True}),
        ("căn từ 3 tỷ", {"price_min": 3.0}),
        # Khoảng hai đầu vẫn tính cả biên — đó là một khoảng, không phải một câu.
        ("căn từ 2 đến 3 tỷ", {"price_min": 2.0, "price_max": 3.0}),
        # "khoảng X" -> nới ±200 triệu.
        ("căn khoảng 3 tỷ", {"price_min": 2.8, "price_max": 3.2}),
        ("căn tầm giá 3 tỷ", {"price_min": 2.8, "price_max": 3.2}),
        ("căn xấp xỉ 2,5 tỷ", {"price_min": 2.3, "price_max": 2.7}),
    ],
)
def test_phan_biet_duoi_khong_qua_va_khoang(query, mong_doi):
    ket_qua = extract_criteria(query)

    for khoa, gia_tri in mong_doi.items():
        assert ket_qua[khoa] == pytest.approx(gia_tri), khoa
    # Không được tự bật cờ nghiêm ngặt cho câu không nói vậy.
    for co in ("price_min_nghiem_ngat", "price_max_nghiem_ngat"):
        if co not in mong_doi:
            assert not ket_qua.get(co), co


def test_khoang_khong_cho_can_duoi_am():
    """ "Khoảng 100 triệu" thì đáy là 0, không phải -0,1."""
    assert extract_criteria("căn khoảng 100 triệu")["price_min"] == 0.0


def test_khoang_lam_tron_theo_do_chinh_xac_cua_gia():
    """0,1 + 0,2 = 0,30000000000000004 và con số đó đi thẳng lên URL portal."""
    assert extract_criteria("căn khoảng 100 triệu")["price_max"] == 0.3


# ---------- Ngữ cảnh do giao diện chèn ----------


def test_ngu_canh_can_dang_xem_khong_nuot_cau_hoi_co_tieu_chi():
    """Ca thật: bấm trích nguồn "VOP237" xong hỏi "còn bao nhiêu căn dưới 3 tỷ".

    FE gắn "(căn đang xem: VOP237)" vào mọi câu không có mã căn, luật "có mã căn
    thì nhường inventory_lookup" khớp phải mã đó, tool tìm kiếm im, và trợ lý
    trả lời "chỉ có thông tin về căn VOP237".
    """
    ket_qua = extract_criteria("còn bao nhiêu căn dưới 3 tỷ (căn đang xem: VOP237)")

    assert ket_qua == {"price_max": 3.0, "price_max_nghiem_ngat": True}


def test_hoi_trong_khong_ve_can_dang_xem_thi_van_nhuong_inventory_lookup():
    """Bỏ ngữ cảnh không được làm hỏng tính năng "phân tích căn hiện tại"."""
    assert extract_criteria("phân tích chi tiết căn này (căn đang xem: VOP237)") is None


def test_nguoi_dung_tu_neu_ma_can_thi_van_nhuong_inventory_lookup():
    assert extract_criteria("căn VOP345 giá bao nhiêu") is None


# ---------- Trần kết quả: "liệt kê" phải liệt kê được ----------


@pytest.mark.asyncio
async def test_du_ca_thi_bao_day_du():
    ket_qua = await InventorySearchTool().run(price_max=3)

    assert ket_qua.data["day_du"]
    assert "ghi_chu" not in ket_qua.data


@pytest.mark.asyncio
async def test_bi_cat_thi_bao_chua_day_du():
    """Model đọc `tong_so_khop`=21 cạnh mảng tên `danh_sach` 8 phần tử vẫn trả
    lời "8 căn" — và nó không sai, tên vậy thì đọc nghĩa đen là danh sách."""
    ket_qua = await InventorySearchTool().run(limit=1)

    assert not ket_qua.data["day_du"]
    assert len(ket_qua.data["can_hien_thi"]) == 1
    assert "đừng đếm" in ket_qua.data["ghi_chu"]


@pytest.mark.asyncio
async def test_hang_tra_ve_da_rut_gon_truong():
    """Bỏ trường thừa mới chở được nhiều căn trong cùng ngân sách token."""
    ket_qua = await InventorySearchTool().run(price_max=3)

    can = ket_qua.data["can_hien_thi"][0]
    assert "unit_code" in can and "price_label" in can
    for thua in ("floor", "room_no", "photos", "price_value", "area_value"):
        assert thua not in can, thua


@pytest.mark.asyncio
async def test_tham_so_model_bia_khong_giet_ca_tool():
    """`sort='price'` từng làm hỏng cả tool và agent mất sạch dữ liệu."""
    ket_qua = await InventorySearchTool().run(price_max=3, sort="price")

    assert ket_qua.ok
    assert ket_qua.data["tong_so_khop"] == 3
    assert ket_qua.data["tieu_chi_bo_qua"] == ["sort"]


# ---------- Phân khu ----------


@pytest.mark.parametrize(
    ("query", "mong_doi"),
    [
        ("căn ở Ocean Park 2", "Ocean Park 2"),
        ("căn OP3 dưới 3 tỷ", "Ocean Park 3"),
        ("phân khu 1 có gì", "Ocean Park 1"),
        ("khu 2 còn căn nào", "Ocean Park 2"),
        ("căn 2PN ở OceanPark 3", "Ocean Park 3"),
        # Mã toà chứa chữ số nhưng KHÔNG phải số phân khu.
        ("tìm căn toà S2", None),
        ("tìm căn toà S210 2PN", None),
        # Dự án chỉ có ba phân khu — bắt "khu 7" rồi lọc ra rỗng thì người dùng
        # không hiểu vì sao.
        ("căn ở khu 7", None),
    ],
)
def test_rut_phan_khu(query: str, mong_doi: str | None):
    assert (extract_criteria(query) or {}).get("subdivision") == mong_doi


@pytest.mark.asyncio
async def test_loc_theo_phan_khu():
    ket_qua = await InventorySearchTool().run(subdivision="Ocean Park 2")

    ma = {r["unit_code"] for r in ket_qua.data["can_hien_thi"]}
    assert ma == {"VOP002", "VOP004"}


@pytest.mark.asyncio
async def test_loc_phan_khu_bo_qua_hoa_va_khoang_trang():
    """Dữ liệu ghi "Ocean Park 2" còn model có thể gửi "oceanpark 2"."""
    ket_qua = await InventorySearchTool().run(subdivision="oceanpark2")

    assert ket_qua.data["tong_so_khop"] == 2


@pytest.mark.asyncio
async def test_phan_khu_ket_hop_voi_gia():
    ket_qua = await InventorySearchTool().run(subdivision="Ocean Park 2", price_max=3, price_max_nghiem_ngat=True)

    assert {r["unit_code"] for r in ket_qua.data["can_hien_thi"]} == {"VOP002"}
