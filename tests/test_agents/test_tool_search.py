"""Test tool tìm căn theo tiêu chí.

Từ vựng lọc phải đọc từ dữ liệu, không từ danh sách viết cứng — nên fixture ở
đây nạp một bộ căn có kiểu ghi KHÔNG thống nhất ('2 PN, 1WC' lẫn '2PN, 2WC') để
bắt đúng lỗi mà cách hardcode '%2PN%' sẽ mắc phải.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools.search import (
    InventorySearchTool,
    _ghi_chu_cat_bot,
    _ghi_chu_sap_xep,
    extract_criteria,
    vocabulary,
)
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
async def test_khong_khop_thi_tra_ket_luan_kem_ly_do():
    """Trước đây khẳng định `data == []`, và chính chỗ đó gây lỗi.

    `ToolsNode` bỏ qua kết quả rỗng y hệt lúc không tool nào chạy, nên trợ lý
    quay ra xin thêm dữ liệu tồn kho ngay sau khi vừa tra xong kho. Xem
    `TestKhongKhopVanLaKetLuan` cuối file.
    """
    result = await InventorySearchTool().run(unit_type="Studio", view_keyword="biển")

    assert result.ok
    assert result.data["tong_so_khop"] == 0
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


class TestSoVeSinh:
    """Số vệ sinh đọc RỜI khỏi số phòng ngủ.

    Lỗi đã xảy ra thật trên dữ liệu production: "2 phòng ngủ và 1 vệ sinh ở
    Ocean Park 3" cho ra **15 căn** — gồm cả 9 căn 2PN-2WC — trong khi đáp án
    đúng là 6. Trợ lý nói sai SỐ LƯỢNG rồi liệt kê cả những căn không khớp yêu
    cầu, chứ không phải chỉ hiển thị dư.

    Nguyên nhân: `_match_unit_type` chỉ có regex đọc phòng ngủ, số vệ sinh trong
    câu bị bỏ qua hoàn toàn và không có dấu hiệu nào báo ra.
    """

    def test_doc_duoc_so_ve_sinh(self) -> None:
        assert extract_criteria("căn 2 phòng ngủ 1 vệ sinh")["wc"] == 1

    @pytest.mark.parametrize(
        "cau",
        ["căn 2WC", "căn 2 wc", "căn 2 nhà vệ sinh", "căn 2 ve sinh", "căn 2 toilet"],
    )
    def test_cac_cach_viet_deu_doc_duoc(self, cau: str) -> None:
        assert extract_criteria(cau)["wc"] == 2

    def test_khong_neu_thi_khong_loc(self) -> None:
        """Không nêu vệ sinh thì phải trả MỌI căn 2PN, không đoán bừa một số."""
        assert "wc" not in extract_criteria("căn 2 phòng ngủ")

    @pytest.mark.asyncio
    async def test_loc_dung_theo_so_ve_sinh(self) -> None:
        """VOP001 là '2 PN, 1WC' (có dấu cách) — phải khớp, VOP002 '2PN, 2WC' thì không."""
        ket_qua = await InventorySearchTool().run(unit_type="2PN", wc=1)

        ma = [c["unit_code"] for c in ket_qua.data["can_hien_thi"]]
        assert ma == ["VOP001"], "VOP005 đã bán nên bị loại, VOP002 là 2WC"

    @pytest.mark.asyncio
    async def test_loc_ve_sinh_khong_can_neu_phong_ngu(self) -> None:
        """Lý do `wc` phải là trường RIÊNG.

        Gộp vào `unit_type` thì không diễn đạt nổi câu này: `unit_type` khớp
        theo TIỀN TỐ, mà số vệ sinh nằm ở đuôi chuỗi.
        """
        ket_qua = await InventorySearchTool().run(wc=1)

        ma = sorted(c["unit_code"] for c in ket_qua.data["can_hien_thi"])
        assert ma == ["VOP001", "VOP004"], "cả 2PN-1WC lẫn 1PN-1WC, không lấy Studio hay 2WC"


class TestKhongKhopVanLaKetLuan:
    """Tra xong không có căn nào là một SỰ THẬT, không phải thiếu dữ liệu.

    Ca thật trên production: "Tìm căn có 2 phòng ngủ và 3 vệ sinh ở Ocean Park 1"
    — kho không có căn 3 vệ sinh nào — và trợ lý trả lời "Mình chưa có đủ dữ
    liệu… bạn cho mình biết thêm dữ liệu tồn kho". Nó vừa tra xong cái kho đó.

    Gốc: tool trả `data=[]`, mà `ToolsNode` bỏ qua kết quả rỗng y hệt lúc không
    tool nào chạy. `generate` mất sạch bằng chứng rồi rơi xuống tài liệu.
    """

    @pytest.mark.asyncio
    async def test_tra_ve_ket_luan_chu_khong_rong(self) -> None:
        ket_qua = await InventorySearchTool().run(unit_type="2PN", wc=3)

        assert ket_qua.ok
        assert ket_qua.data, "data rỗng thì ToolsNode bỏ qua và bằng chứng biến mất"
        assert ket_qua.data["tong_so_khop"] == 0

    @pytest.mark.asyncio
    async def test_ke_ra_loai_can_dang_co(self) -> None:
        """Để trợ lý nói được câu hữu ích thay vì một lời từ chối cụt."""
        ket_qua = await InventorySearchTool().run(unit_type="2PN", wc=3)

        dang_co = ket_qua.data["loai_can_dang_co"]
        assert "2PN, 2WC" in dang_co
        assert all("3WC" not in v for v in dang_co), "không được kê loại vốn không có"

    @pytest.mark.asyncio
    async def test_giu_cac_tieu_chi_khac_khi_noi_long(self) -> None:
        """Chỉ nới hình dạng căn, KHÔNG nới toà — nới hết thì kê cả căn ở nơi khác."""
        ket_qua = await InventorySearchTool().run(building="R103", unit_type="2PN", wc=3)

        assert ket_qua.data["loai_can_dang_co"] == ["Studio"], "R103 chỉ có Studio"

    @pytest.mark.asyncio
    async def test_nhan_nguon_khong_phai_ten_tool(self) -> None:
        """Không có mã căn nào để trỏ vào, nhãn phải là chữ người đọc hiểu."""
        from src.agents.nodes.tools import _nguon_cua_tool

        tool = InventorySearchTool()
        nguon = _nguon_cua_tool(tool, await tool.run(unit_type="2PN", wc=3))

        assert [c.title for c in nguon] == ["Dữ liệu tồn kho"]

    @pytest.mark.asyncio
    async def test_kho_rong_thi_khong_duoc_ket_luan_chac_chan(self, monkeypatch) -> None:
        """Kho rỗng hoàn toàn khác hẳn "lọc xong không còn căn nào".

        `database_url` thiếu thì rơi về `sqlite:///./data/app.db` — một file
        rỗng trong container (xem render.yaml). Lúc đó tuyên bố "đã tra hết kho
        và không có căn nào" là nói chắc chắn một điều SAI, tệ hơn hẳn việc
        nhận là chưa đủ dữ liệu.
        """
        from src.agents.tools import search as mod

        class KhoRong:
            def query_units(self, **_kwargs):
                return []

        monkeypatch.setattr(mod, "get_inventory_db", lambda: KhoRong())
        ket_qua = await InventorySearchTool().run(unit_type="2PN")

        assert ket_qua.data == [], "kho rỗng thì không được kết luận gì"


class TestGhiChuKhongLoChiTietKyThuat:
    """`ghi_chu` viết CHO MODEL đọc, nhưng model diễn giải lại cho KHÁCH.

    Bản trước viết "`can_hien_thi` chỉ là 30 căn đầu" — nhắc thẳng tên trường và
    con số, nên model tưởng đó là thông tin cần truyền đạt. Đo trên production,
    tái hiện ở cả hai lần chạy eval:

        "Có 43 căn ở Ocean Park 2 khớp dữ liệu; hiện ngữ cảnh cung cấp chi tiết
         30 căn đầu, nên mình liệt kê các căn này…"

    Trợ lý đang kể cho khách nghe về ngữ cảnh của chính nó — vô nghĩa với người
    mua nhà, và nghe như hệ thống đang giấu 13 căn.
    """

    def test_khong_nhac_ten_truong_du_lieu(self) -> None:
        ghi_chu = _ghi_chu_cat_bot(43)

        assert "can_hien_thi" not in ghi_chu

    def test_khong_neu_so_can_dang_hien_thi(self) -> None:
        """Chỉ có TỔNG được nêu. Con số 30 lọt vào là model sẽ đọc nó ra."""
        ghi_chu = _ghi_chu_cat_bot(43)

        assert "43" in ghi_chu
        assert "30" not in ghi_chu

    def test_cam_tuong_minh_viec_ke_lai_cho_nguoi_dung(self) -> None:
        ghi_chu = _ghi_chu_cat_bot(43).lower()

        assert "không nói với người dùng" in ghi_chu

    def test_ghi_chu_sap_xep_cung_khong_moi_giai_thich_co_che(self) -> None:
        ghi_chu = _ghi_chu_sap_xep("gia_tang", 12).lower()

        assert "không cần giải thích cơ chế" in ghi_chu
