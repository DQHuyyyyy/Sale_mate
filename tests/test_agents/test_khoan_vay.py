"""Test tool tính khoản vay.

Trọng tâm là những chỗ tool ĐƯỢC PHÉP im lặng và những chỗ nó TỪ CHỐI đoán —
đó mới là lý do tool tồn tại. Ca thật đã hỏng: model có giá căn từ tool tồn kho
rồi tự thêm "ngân hàng cho vay lên đến 70-80% giá trị", con số không có trong
tài liệu nào.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.agents.tools.chinh_sach_vay import (
    chinh_sach_dang_ap_dung,
    chinh_sach_gan_nhat_da_het,
    tai_chinh_sach,
)
from src.agents.tools.khoan_vay import TinhKhoanVayTool, _rut_tham_so, _tra_hang_thang

# Trong thời gian áp dụng của chính sách 6% (20/4 - 20/7/2026).
NGAY_CON_HAN = date(2026, 5, 15)
# Sau khi chính sách hết hạn — đúng tình huống hiện tại của hệ thống.
NGAY_HET_HAN = date(2026, 8, 13)


@pytest.fixture
def ngay(monkeypatch: pytest.MonkeyPatch):
    """Cố định "hôm nay" cho tool. Chính sách có hạn nên test phụ thuộc ngày."""

    def dat(gia_tri: date) -> None:
        class _Ngay(date):
            @classmethod
            def today(cls) -> date:
                return gia_tri

        monkeypatch.setattr("src.agents.tools.khoan_vay.date", _Ngay)

    return dat


# ---------- Hiệu lực theo ngày ----------


def test_ngoai_thoi_gian_ap_dung_thi_khong_co_chinh_sach_nao():
    """Giữa hai đợt chính sách thì đúng là không có ưu đãi — trả None là hợp lệ."""
    assert chinh_sach_dang_ap_dung(NGAY_HET_HAN) is None
    assert chinh_sach_dang_ap_dung(NGAY_CON_HAN) is not None


def test_chinh_sach_moi_de_len_chinh_sach_cu():
    """20/3/2026 công bố trần 9%, tới 17/4 hạ xuống 6% — không được lẫn hai bản."""
    assert chinh_sach_dang_ap_dung(date(2026, 4, 1)).tran_lai_suat == 9.0
    assert chinh_sach_dang_ap_dung(date(2026, 5, 1)).tran_lai_suat == 6.0


def test_biet_chinh_sach_gan_nhat_da_het_ngay_nao():
    """Nói "chưa có chính sách nào" thì khách tưởng chưa bao giờ có."""
    da_het = chinh_sach_gan_nhat_da_het(NGAY_HET_HAN)
    assert da_het is not None
    assert da_het.hieu_luc_den == date(2026, 7, 20)


def test_moi_chinh_sach_deu_tro_ve_mot_tai_lieu_nguon():
    """Không có `doc_id` thì câu trả lời không trích nguồn được."""
    for cs in tai_chinh_sach():
        assert cs.doc_id, f"{cs.ma} thiếu doc_id"


# ---------- Từ chối đoán ----------


@pytest.mark.asyncio
async def test_het_han_thi_khong_sinh_ra_lai_suat_nao(ngay):
    """Rơi về chính sách gần nhất trông thì hữu ích, nhưng là báo cho khách một
    ưu đãi họ không được hưởng."""
    ngay(NGAY_HET_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=2.25, von_tu_co=1.0)

    assert ket_qua.ok
    assert ket_qua.data["chinh_sach_ho_tro_lai_suat"] is None
    assert "tra_hang_thang_trieu" not in ket_qua.data
    assert "KHÔNG có chính sách" in ket_qua.data["canh_bao"]
    # Vẫn phải nói rõ bản gần nhất hết ngày nào.
    assert ket_qua.data["chinh_sach_gan_nhat_da_het_han"]["het_hieu_luc_ngay"] == "2026-07-20"


@pytest.mark.asyncio
async def test_vuot_muc_ho_tro_thi_khong_tinh_tra_gop(ngay):
    """Tính theo trần 6% khi chính sách không phủ tỷ lệ đó là ngụ ý sai."""
    ngay(NGAY_CON_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=4.0, von_tu_co=0.6)  # vay 85%

    assert ket_qua.data["ty_le_vay_phan_tram"] == 85.0
    assert "tra_hang_thang_trieu" not in ket_qua.data
    assert "vượt mức hỗ trợ cao nhất" in ket_qua.data["canh_bao"]


@pytest.mark.asyncio
async def test_luon_noi_ro_sau_ky_khoa_tran_la_chua_xac_dinh(ngay):
    """Lãi suất sau giai đoạn khoá là thả nổi — không được im lặng bỏ qua."""
    ngay(NGAY_CON_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=2.25, von_tu_co=1.0)

    assert "chưa xác định" in ket_qua.data["sau_khi_het_khoa_tran"]


# ---------- Phép tính ----------


def test_tra_hang_thang_dung_cong_thuc_nien_kim():
    """1,25 tỷ ở 6%/năm trong 20 năm = 8,96 triệu/tháng."""
    assert _tra_hang_thang(1.25, 6.0, 240) == pytest.approx(0.008956, abs=1e-5)


def test_lai_suat_0_khong_chia_cho_khong():
    """Gói 18 tháng miễn lãi hoàn toàn — công thức niên kim chia 0 ở đây."""
    assert _tra_hang_thang(1.2, 0.0, 12) == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_von_du_mua_thi_khong_can_vay(ngay):
    ngay(NGAY_CON_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=2.0, von_tu_co=2.5)

    assert ket_qua.data["can_vay_ty"] == 0


@pytest.mark.asyncio
async def test_phu_phi_goi_la_phan_tram_cong_vao_gia_khong_phai_lai_suat(ngay):
    """Nhầm phụ phí với lãi suất là sai số hàng trăm triệu."""
    ngay(NGAY_CON_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=2.0, von_tu_co=1.0)  # vay 50% -> mức 70%

    goi_24 = next(g for g in ket_qua.data["cac_goi_ho_tro"] if g["so_thang_ho_tro"] == 24)
    assert goi_24["phu_phi_phan_tram"] == 4.5
    assert goi_24["phu_phi_ty"] == pytest.approx(0.09)
    assert goi_24["gia_sau_phu_phi_ty"] == pytest.approx(2.09)


@pytest.mark.asyncio
async def test_muc_vay_lay_bac_nho_nhat_phu_du(ngay):
    """Vay 55% rơi vào mức 70%, không phải 80% — phụ phí ở bậc thấp nhẹ hơn."""
    ngay(NGAY_CON_HAN)

    ket_qua = await TinhKhoanVayTool().run(gia_can=2.25, von_tu_co=1.0)

    assert ket_qua.data["muc_vay_ap_dung_phan_tram"] == 70


# ---------- build_args: khi nào tool được chạy ----------


@pytest.mark.parametrize(
    ("query", "mong_doi"),
    [
        (
            "hiện tại tôi có 1 tỷ và tôi muốn mua căn VOP397 thì có khoản vay nào",
            {"unit_code": "VOP397", "von_tu_co": 1.0},
        ),
        ("tôi có 800 triệu muốn vay mua VOP345", {"unit_code": "VOP345", "von_tu_co": 0.8}),
        ("tôi có 1.500.000.000 muốn trả góp căn VOP217", {"unit_code": "VOP217", "von_tu_co": 1.5}),
        # Có vốn, không có mã căn -> việc của inventory_search.
        ("tôi có 2 tỷ, còn căn nào không", None),
        # Có mã căn, không nêu vốn -> không biết vay bao nhiêu.
        ("căn VOP397 giá bao nhiêu", None),
        # Có cả hai nhưng không hỏi vay -> đừng chen vào.
        ("tôi có 2 tỷ, căn VOP397 còn không", None),
    ],
)
def test_rut_tham_so(query: str, mong_doi: dict | None):
    assert _rut_tham_so(query) == mong_doi


class TestTrichNguonVeTaiLieuChinhSach:
    """Mọi con số định lượng của tool này đến từ `chinh_sach_vay.json`, mà file
    đó khai sẵn `doc_id` trỏ về tài liệu văn bản gốc — chính là để câu trả lời
    trích ngược được.

    Trước đây tool trả `source="tool:tinh_khoan_vay"`, nên dòng "Nguồn" hiện
    `"tinh_khoan_vay"`: một cái tên máy, bấm vào không ra gì, và người đọc không
    biết con số 6%/năm đến từ đâu để kiểm.
    """

    @pytest.mark.asyncio
    async def test_source_tro_ve_tai_lieu_chinh_sach(self) -> None:
        from src.agents.tools.khoan_vay import TinhKhoanVayTool

        kq = await TinhKhoanVayTool().run(gia_can=2.7, von_tu_co=0.81)

        assert kq.source.startswith("knowledge:")

    @pytest.mark.asyncio
    async def test_nguon_bam_duoc_va_qua_duoc_bo_loc(self) -> None:
        """`kind` vẫn là "db" dù trỏ vào tài liệu.

        Đặt `kind="doc"` thì `loc_nguon_da_dung` đòi model gọi tên tài liệu mới
        giữ — luật đó đúng cho chunk truy hồi (chỉ "đã tra") nhưng sai cho tool
        (đã DÙNG thật), và câu trả lời mất sạch nguồn cho chính khẳng định của nó.
        """
        from src.agents.nguon import loc_nguon_da_dung
        from src.agents.nodes.tools import _nguon_cua_tool
        from src.agents.tools.khoan_vay import TinhKhoanVayTool

        tool = TinhKhoanVayTool()
        nguon = _nguon_cua_tool(tool, await tool.run(gia_can=2.7, von_tu_co=0.81))

        assert nguon[0].kind == "db"
        assert nguon[0].doc_id.startswith("knowledge:")
        # Nhãn là TÊN tài liệu, không phải tên tool.
        assert "tinh_khoan_vay" not in nguon[0].title

        giu = loc_nguon_da_dung(nguon, "Cần vay 1,89 tỷ đồng.", co_du_lieu_tool=True)
        assert len(giu) == 1, "nguồn tool phải sống sót dù model không gọi tên tài liệu"


def test_doc_id_trong_chinh_sach_tro_ve_tai_lieu_co_that() -> None:
    """Chốt chặn chống trôi lệch: `doc_id` khai trong JSON phải khớp một tài
    liệu đang có trong `data/raw/knowledge/`.

    Đổi tên file tài liệu mà quên sửa JSON thì nút trích nguồn dẫn tới 404 —
    im lặng, chỉ người dùng bấm vào mới biết.
    """
    from src.agents.tools.chinh_sach_vay import tai_chinh_sach
    from src.data.sources.knowledge_docs import load_knowledge_dir

    co_that = {d.doc_id for d in load_knowledge_dir()}
    khai = {cs.doc_id for cs in tai_chinh_sach() if cs.doc_id}

    assert khai, "chinh_sach_vay.json phải khai doc_id để câu trả lời trích ngược được"
    assert khai <= co_that, f"doc_id không có tài liệu tương ứng: {sorted(khai - co_that)}"
