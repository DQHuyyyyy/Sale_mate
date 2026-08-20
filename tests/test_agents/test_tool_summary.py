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
    assert ket_qua.data["dang_ban"] == 3
    assert ket_qua.data["da_ban"] == 2


@pytest.mark.asyncio
async def test_chi_thong_ke_can_con_trong_theo_toa():
    """Sale cần biết còn gì để chào khách, không cần phân bố của căn đã bán."""
    ket_qua = await InventorySummaryTool().run()

    assert ket_qua.data["dang_ban_theo_toa"] == {"R103": 1, "S210": 2}


@pytest.mark.asyncio
async def test_loc_theo_toa():
    ket_qua = await InventorySummaryTool().run(building="S210")

    assert ket_qua.data["tong_so_can"] == 3
    assert ket_qua.data["dang_ban"] == 2


@pytest.mark.asyncio
async def test_khong_khop_thi_bao_ro_chu_khong_no():
    ket_qua = await InventorySummaryTool().run(building="KHONG-CO")

    assert ket_qua.ok
    # Vẫn phải nói rõ đã tìm ở ĐÂU. "Không có căn nào" trơ trọi thì model không
    # biết là không có trong toà đó hay không có trong cả kho.
    assert ket_qua.data == {"pham_vi": {"building": "KHONG-CO"}}
    assert "KHONG-CO" in ket_qua.error


@pytest.mark.asyncio
async def test_db_hong_thi_tra_failure_khong_raise(monkeypatch):
    class _Hong:
        def query_units(self, **kwargs):
            raise ConnectionError("mất kết nối")

    monkeypatch.setattr("src.agents.tools.summary.get_inventory_db", lambda: _Hong())

    ket_qua = await InventorySummaryTool().run()

    assert ket_qua.ok is False
    assert "không truy vấn được" in ket_qua.error.lower()


class TestNguCanhWidgetKhongLamTatToolDem:
    """Ca thật (ảnh 3): đang mở VOP758 rồi hỏi "Ocean Park 3 còn bao nhiêu căn
    đang bán?" — FE gắn "(căn đang xem: VOP758)", luật "có mã căn thì nhường
    inventory_lookup" khớp phải mã do FE chèn, tool đếm im, và trợ lý trả lời
    "chưa đủ dữ liệu… căn đang xem là VOP758 thuộc Ocean Park 1".
    """

    CAU = "Ocean Park 3 còn bao nhiêu căn đang bán? (căn đang xem: VOP758)"

    def test_van_dem_dung_phan_khu(self) -> None:
        assert _extract_args(self.CAU) == {"subdivision": "Ocean Park 3"}

    def test_lookup_khong_bam_vao_ma_do_fe_chen(self) -> None:
        """Tra một căn không liên quan chỉ nhồi nhiễu vào prompt."""
        from src.agents.tools.inventory import _extract_args as lookup_args

        assert lookup_args(self.CAU) is None

    def test_tim_kiem_nhuong_cho_tool_dem(self) -> None:
        """Chạy cả hai thì dòng "Nguồn" của câu "còn 30 căn" hoá ra ba mã căn
        ngẫu nhiên — không mã nào là bằng chứng cho con số 30."""
        from src.agents.tools.search import extract_criteria

        assert extract_criteria(self.CAU) is None

    def test_nguoi_dung_tu_go_ma_can_thi_van_nhuong_lookup(self) -> None:
        """Chốt ngược: mã căn do NGƯỜI DÙNG gõ vẫn phải thắng."""
        assert _extract_args("Căn VOP758 còn bao nhiêu tiền?") is None

    def test_xem_danh_sach_thi_khong_bi_coi_la_cau_dem(self) -> None:
        """ "đã bán" là dấu hiệu của summary nhưng người dùng xin DANH SÁCH."""
        from src.agents.tools.search import extract_criteria

        assert extract_criteria("Cho tôi xem các căn đã bán ở Ocean Park 1") is not None


class TestPhamViPhaiDiKemConSo:
    """Ca thật: "Ocean Park 3 còn bao nhiêu căn đang bán?" — tool lọc đúng OP3,
    trả `con_trong: 30`, mà trợ lý vẫn nói "chưa xác định số đó thuộc Ocean Park
    3 hay các phân khu khác" rồi từ chối.

    Con số tổng hợp không kèm phạm vi thì mọi khẳng định dựng trên nó đều là
    đoán — model từ chối là đúng. Lỗi nằm ở tool, không ở model.
    """

    @pytest.mark.asyncio
    async def test_tra_lai_bo_loc_da_ap_dung(self) -> None:
        ket_qua = await InventorySummaryTool().run(subdivision="Ocean Park 1")

        assert ket_qua.data["pham_vi"] == {"subdivision": "Ocean Park 1"}

    @pytest.mark.asyncio
    async def test_dem_ca_kho_thi_noi_ro_la_ca_kho(self) -> None:
        ket_qua = await InventorySummaryTool().run()

        assert ket_qua.data["pham_vi"] == {}
        assert ket_qua.data["mo_ta_pham_vi"] == "toàn bộ tồn kho"

    @pytest.mark.asyncio
    async def test_dat_ten_theo_ve_nguoi_mua_hay_hoi(self) -> None:
        """ "đang bán" và "còn trống" là một — đừng bắt model bắc cầu."""
        ket_qua = await InventorySummaryTool().run()

        assert "dang_ban" in ket_qua.data
        assert "con_trong" not in ket_qua.data
