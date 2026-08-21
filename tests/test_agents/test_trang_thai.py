"""Test ba trạng thái căn: Còn / Đã đặt cọc / Đã bán.

Vì sao cần: `dat_coc_lead` ghi lead xong thì trước đây KHÔNG có gì đổi. Đo ngày
19/08/2026 trên production: hai lead thật (VOP397, VOP908) đều `trang_thai='new'`
mà cả hai căn vẫn hiện "Còn" ở cả portal lẫn chatbot — trợ lý tiếp tục chào hai
căn đó cho khách mới như chưa ai hỏi.

Trạng thái được suy trong VIEW `inventory_units` từ `dat_coc_lead`
([migration 010](../../interface/backend/migrations/010_trang_thai_dat_coc.sql)),
nên ở đây chỉ cần nạp sẵn `status` vào bảng giả và kiểm hành vi của từng tool.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.agents.tools import trang_thai as tt
from src.agents.tools.search import InventorySearchTool, vocabulary
from src.agents.tools.summary import InventorySummaryTool
from src.data.stores.inventory_db import InventoryDB, inventory_units_table, metadata


def _row(code: str, status: str, price: float = 3.0) -> dict:
    return {
        "unit_code": code,
        "building": "S210",
        "floor": "10",
        "room_no": "1001",
        "unit_type": "2PN, 1WC",
        "area_m2": "60m2",
        "direction": "Đông Nam",
        "view": "View hồ",
        "legal_status": "Sẵn sổ",
        "price_label": f"{price} tỷ",
        "furniture": "Cơ bản",
        "status": status,
        "photos": [],
        "price_value": price,
        "area_value": 60.0,
        "subdivision": "Ocean Park 1",
    }


_KHO = [
    _row("VOP001", tt.CON),
    _row("VOP002", tt.CON),
    _row("VOP003", tt.DA_DAT_COC),
    _row("VOP004", tt.DA_DAT_COC),
    _row("VOP005", tt.DA_BAN),
]


@pytest.fixture(autouse=True)
def _kho_gia(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine, tables=[inventory_units_table])
    with engine.begin() as conn:
        conn.execute(inventory_units_table.insert(), _KHO)

    db = InventoryDB("sqlite:///:memory:", engine=engine)
    for mo_dun in ("search", "summary", "dat_coc"):
        monkeypatch.setattr(f"src.agents.tools.{mo_dun}.get_inventory_db", lambda: db)
    vocabulary.clear()
    yield
    vocabulary.clear()


class TestBangNhan:
    """Một bảng nhãn duy nhất. Trước đây `inventory.py` và `so_sanh.py` mỗi bên
    giữ một bản chép — thêm trạng thái mà sửa một bên là cùng một căn hiện hai
    nhãn khác nhau tuỳ vào việc khách hỏi kiểu gì."""

    @pytest.mark.parametrize(
        ("status", "mong_doi"),
        [
            (tt.CON, "Còn"),
            (tt.DA_DAT_COC, "Đã đặt cọc"),
            (tt.DA_BAN, "Đã bán"),
        ],
    )
    def test_nhan_tieng_viet(self, status: str, mong_doi: str) -> None:
        assert tt.nhan(status) == mong_doi

    def test_gia_tri_la_thi_tra_nguyen_van(self) -> None:
        """Không nuốt thành "Không rõ": dữ liệu sinh trạng thái ngoài bảng thì
        phải nhìn thấy nó để đi sửa."""
        assert tt.nhan("trang_thai_moi") == "trang_thai_moi"

    def test_chi_con_moi_ban_duoc_cho_khach_moi(self) -> None:
        assert tt.con_ban_duoc(tt.CON)
        assert not tt.con_ban_duoc(tt.DA_DAT_COC)
        assert not tt.con_ban_duoc(tt.DA_BAN)


class TestTimKiem:
    @pytest.mark.asyncio
    async def test_van_hien_can_dang_giu_cho_va_da_dat_coc(self) -> None:
        """Cọc có thể huỷ. Giấu hẳn là chào thiếu hàng, và khách đang xem dở một
        căn rồi quay lại thấy nó biến mất thì không có lời giải thích nào."""
        ket_qua = await InventorySearchTool().run(subdivision="Ocean Park 1")

        ma = [c["unit_code"] for c in ket_qua.data["can_hien_thi"]]

        assert "VOP003" in ma
        assert "VOP004" in ma

    @pytest.mark.asyncio
    async def test_khong_bao_gio_hien_can_da_ban(self) -> None:
        ket_qua = await InventorySearchTool().run(subdivision="Ocean Park 1")

        assert "VOP005" not in [c["unit_code"] for c in ket_qua.data["can_hien_thi"]]

    @pytest.mark.asyncio
    async def test_moi_can_kem_nhan_tinh_trang(self) -> None:
        """Thiếu nhãn thì model đọc danh sách rồi chào tất cả như nhau — khách
        gọi hỏi mua một căn đã có người đặt."""
        ket_qua = await InventorySearchTool().run(subdivision="Ocean Park 1")

        theo_ma = {c["unit_code"]: c["status_label"] for c in ket_qua.data["can_hien_thi"]}

        assert theo_ma["VOP001"] == "Còn"
        assert theo_ma["VOP003"] == "Đã đặt cọc"
        assert theo_ma["VOP004"] == "Đã đặt cọc"


class TestDem:
    @pytest.mark.asyncio
    async def test_dem_bon_nhom_roi_nhau(self) -> None:
        """Bản cũ tính `da_ban = tổng − còn trống`, nên hai căn đã đặt cọc bị
        gộp vào "đã bán" — báo cho sale rằng căn đã mất trong khi cọc còn có
        thể huỷ."""
        ket_qua = await InventorySummaryTool().run()

        assert ket_qua.data["tong_so_can"] == 5
        assert ket_qua.data["dang_ban"] == 2
        assert ket_qua.data["da_dat_coc"] == 2
        assert ket_qua.data["da_ban"] == 1

    @pytest.mark.asyncio
    async def test_bon_nhom_cong_lai_bang_tong(self) -> None:
        d = (await InventorySummaryTool().run()).data

        assert d["dang_ban"] + d["da_dat_coc"] + d["da_ban"] == d["tong_so_can"]

    @pytest.mark.asyncio
    async def test_thong_ke_theo_toa_chi_dem_can_dang_ban(self) -> None:
        ket_qua = await InventorySummaryTool().run()

        assert ket_qua.data["dang_ban_theo_toa"] == {"S210": 2}


class TestDatCoc:
    """Không hứa một căn cho hai người."""

    @pytest.mark.asyncio
    async def test_tu_choi_can_da_co_nguoi_giu(self, monkeypatch) -> None:
        from src.agents.tools.dat_coc import DatCocTool

        ket_qua = await DatCocTool().run(unit_code="VOP003", so_dien_thoai="0912345678", ho_ten="Nam")

        assert ket_qua.data["trang_thai"] == "da_co_nguoi_giu"
        assert ket_qua.data["tinh_trang_can"] == "Đã đặt cọc"

    @pytest.mark.asyncio
    async def test_tu_choi_can_da_ban(self) -> None:
        from src.agents.tools.dat_coc import DatCocTool

        ket_qua = await DatCocTool().run(unit_code="VOP005", so_dien_thoai="0912345678")

        assert ket_qua.data["trang_thai"] == "da_co_nguoi_giu"

    @pytest.mark.asyncio
    async def test_khong_neu_so_tien_coc_hay_thoi_han(self) -> None:
        """Hệ thống không có dữ liệu nào về số tiền cọc, thời hạn giữ chỗ hay
        mức phạt — nên tuyệt đối không được nhắc tới."""
        from src.agents.tools.dat_coc import DatCocTool

        ket_qua = await DatCocTool().run(unit_code="VOP003", so_dien_thoai="0912345678")

        chu = str(ket_qua.data)
        assert not any(don_vi in chu for don_vi in ("tỷ", "triệu", "VNĐ", "đồng", "%"))

    @pytest.mark.asyncio
    async def test_can_con_thi_van_ghi_lead_binh_thuong(self) -> None:
        """Chốt ngược: chốt chặn mới không được chặn nhầm đường đi chính."""
        from src.agents.tools.dat_coc import DatCocTool

        ket_qua = await DatCocTool().run(unit_code="VOP001", so_dien_thoai="0912345678", ho_ten="Nam")

        assert ket_qua.data["trang_thai"] == "da_ghi_nhan"

    @pytest.mark.asyncio
    async def test_ton_kho_hong_thi_van_ghi_duoc_lead(self, monkeypatch) -> None:
        """Mất một lead là mất một khách thật đang muốn mua. Ghi thừa một lead
        trùng thì đội sale gọi điện là biết ngay — hai lỗi không cùng hạng."""
        from src.agents.tools.dat_coc import DatCocTool

        class _Hong:
            def query_units(self, **kwargs):
                raise ConnectionError("mất kết nối")

        monkeypatch.setattr("src.agents.tools.dat_coc.get_inventory_db", lambda: _Hong())

        ket_qua = await DatCocTool().run(unit_code="VOP001", so_dien_thoai="0912345678")

        assert ket_qua.data["trang_thai"] == "da_ghi_nhan"

    @pytest.mark.asyncio
    async def test_mot_so_khong_giu_qua_nhieu_can(self, monkeypatch) -> None:
        """Phanh chống khoá sạch tồn kho, phía widget chat.

        Nút "Đặt cọc" trên portal chặn y hệt. Chặn một đường thôi là vô nghĩa —
        đường còn lại vẫn mở, và lead `new` làm căn thành "Đang giữ chỗ" mà giữ
        chỗ không tự hết hạn.
        """
        from src.agents.tools.dat_coc import DatCocTool

        class _DaGiuNhieu:
            def so_can_dang_giu(self, sdt):
                return 3

            def da_co_hom_nay(self, *a):
                return False

            def ghi_lead(self, **k):
                raise AssertionError("Không được ghi thêm khi đã chạm trần")

        monkeypatch.setattr("src.agents.tools.dat_coc.get_dat_coc_db", lambda: _DaGiuNhieu())

        ket_qua = await DatCocTool().run(unit_code="VOP001", so_dien_thoai="0912345678")

        assert ket_qua.data["trang_thai"] == "giu_qua_nhieu"
