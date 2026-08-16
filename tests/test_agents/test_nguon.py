"""Test lọc nguồn — chỉ giữ thứ câu trả lời thật sự dùng.

Ca thật trên production: hỏi "Căn ở Ocean Park 1", trả lời ba căn OP1, mà dòng
nguồn liệt kê tổng quan OP2, tổng quan OP3, ưu đãi OP2 và cả description của
tool. Trích nguồn vốn để chứng minh trợ lý không bịa; chỉ vào thứ không liên
quan thì người đọc mất niềm tin vào cả những nguồn đúng.
"""

from __future__ import annotations

from src.agents.nguon import TOI_DA_NGUON_TAI_LIEU, loc_nguon_da_dung
from src.models.chat import Citation


def _doc(ten: str) -> Citation:
    return Citation(doc_id=ten, title=ten, kind="doc")


def _db(ma: str) -> Citation:
    return Citation(doc_id="inventory:postgres", title=ma, kind="db")


class TestNguonDuLieu:
    def test_chi_giu_ma_can_co_trong_cau_tra_loi(self) -> None:
        nguon = [_db("VOP758"), _db("VOP285"), _db("VOP893")]

        giu = loc_nguon_da_dung(nguon, "Căn VOP758 và VOP285 đều còn trống.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP758", "VOP285"]

    def test_khong_khop_ma_gan_giong(self) -> None:
        """VOP61 không được ăn theo VOP619.

        Phải có ít nhất một mã khớp, nếu không lưới dự phòng sẽ giữ lại tất cả
        và che mất đúng thứ test này muốn kiểm.
        """
        giu = loc_nguon_da_dung([_db("VOP61"), _db("VOP619")], "Căn VOP619 giá 3,850 tỷ.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP619"]

    def test_khong_phan_biet_hoa_thuong(self) -> None:
        giu = loc_nguon_da_dung([_db("VOP758")], "căn vop758 còn trống", co_du_lieu_tool=True)

        assert len(giu) == 1

    def test_khong_xoa_sach_khi_cau_tra_loi_khong_nhac_ma(self) -> None:
        """Không nhắc lại mã không có nghĩa là số liệu tự nhiên mà có."""
        nguon = [_db("VOP345")]

        giu = loc_nguon_da_dung(nguon, "Căn này giá 2,7 tỷ, vẫn còn trống.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP345"]

    def test_luoi_du_phong_cung_co_tran(self) -> None:
        nguon = [_db(f"VOP{i:03d}") for i in range(1, 10)]

        giu = loc_nguon_da_dung(nguon, "Có 9 căn phù hợp.", co_du_lieu_tool=True)

        assert len(giu) == TOI_DA_NGUON_TAI_LIEU


class TestNguonTaiLieu:
    def test_luot_co_tool_thi_tai_lieu_phai_duoc_nhac_den(self) -> None:
        """Ca trong ảnh: trả lời về căn OP1, nguồn lại có tài liệu OP2 và OP3."""
        nguon = [
            _doc("Tổng quan dự án Vinhomes Ocean Park 2"),
            _doc("Ưu đãi của Vinhomes OceanPark 2"),
            _db("VOP758"),
        ]

        giu = loc_nguon_da_dung(nguon, "Căn VOP758 giá 2,750 tỷ.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP758"]

    def test_luot_khong_co_tool_thi_giu_vai_tai_lieu_dau(self) -> None:
        """Không có tool thì câu trả lời chắc chắn dựng từ tài liệu."""
        nguon = [_doc(f"Tài liệu {i}") for i in range(6)]

        giu = loc_nguon_da_dung(nguon, "Dự án có biển hồ nước mặn.", co_du_lieu_tool=False)

        assert [c.title for c in giu] == ["Tài liệu 0", "Tài liệu 1", "Tài liệu 2"]

    def test_giu_tai_lieu_model_trich_ten_tuong_minh(self) -> None:
        nguon = [_doc("Chính sách hỗ trợ lãi suất chung của Vinhomes"), _db("VOP758")]
        tra_loi = "Theo Chính sách hỗ trợ lãi suất chung của Vinhomes, căn VOP758 được hỗ trợ."

        giu = loc_nguon_da_dung(nguon, tra_loi, co_du_lieu_tool=True)

        assert len(giu) == 2

    def test_so_khop_ten_tai_lieu_bo_qua_dau(self) -> None:
        giu = loc_nguon_da_dung([_doc("Vị trí Ocean Park")], "Theo vi tri ocean park thì...", co_du_lieu_tool=True)

        assert len(giu) == 1


class TestBienAnToan:
    def test_chua_co_chu_nao_thi_giu_nguyen(self) -> None:
        """Lỗi giữa chừng không được biến thành 'câu trả lời không có nguồn'."""
        nguon = [_doc("Tài liệu A"), _db("VOP758")]

        assert loc_nguon_da_dung(nguon, "", co_du_lieu_tool=True) == nguon

    def test_bo_nguon_khong_co_nhan(self) -> None:
        giu = loc_nguon_da_dung([Citation(doc_id="x", title="", kind="doc")], "abc", co_du_lieu_tool=False)

        assert giu == []
