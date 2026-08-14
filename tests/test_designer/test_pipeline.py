"""Test pipeline ảnh — phần quyết định ảnh ra có đúng hay không.

Toàn bộ hàm ở đây là hàm thuần: không gọi model, không chạm mạng, chạy trong
mili-giây. Nhờ vậy test được kỹ đúng chỗ đáng test nhất.

Bài quan trọng nhất là `TestGhepDe`: nó chứng minh vùng ngoài khung sửa giữ
nguyên TỪNG PIXEL. Model không bảo đảm được điều đó — tài liệu OpenAI nói mask
chỉ là gợi ý — nên chốt bảo đảm nằm ở đây, và nếu nó vỡ thì trợ lý âm thầm trả
về ảnh căn hộ bị vẽ lại chỗ khác mà không ai biết.
"""

from __future__ import annotations

import pytest
from PIL import Image

from src.designer.pipeline import (
    BOI_SO,
    Vung,
    chuan_hoa_kich_thuoc,
    doc_anh,
    dong_nhan,
    dung_mask,
    ghep_de,
    xuat_png,
)


def _anh(mau: tuple[int, int, int], kich_thuoc: tuple[int, int] = (200, 100)) -> Image.Image:
    return Image.new("RGB", kich_thuoc, mau)


DO = (255, 0, 0)
XANH = (0, 0, 255)


def _so_pixel_pha(anh: Image.Image) -> int:
    """Đếm pixel không thuần đỏ cũng không thuần xanh — tức dải chuyển tiếp."""
    return sum(1 for mau in anh.getdata() if mau not in (DO, XANH))


# ---------- Chuẩn hoá kích thước ----------


class TestChuanHoaKichThuoc:
    def test_moi_canh_deu_la_boi_so_16(self):
        for rong, cao in [(4032, 3024), (1920, 1080), (777, 501), (100, 250)]:
            w, h = chuan_hoa_kich_thuoc(rong, cao, canh_toi_da=1536)
            assert w % BOI_SO == 0 and h % BOI_SO == 0, (rong, cao, w, h)

    def test_thu_nho_anh_dien_thoai_ve_duoi_tran(self):
        w, h = chuan_hoa_kich_thuoc(4032, 3024, canh_toi_da=1536)

        assert max(w, h) <= 1536
        assert abs(w / h - 4032 / 3024) < 0.02  # ty le giu gan nhu nguyen

    def test_khong_phong_to_anh_nho(self):
        """Phóng to là bịa thêm pixel không có thật, và tốn tiền hơn."""
        w, h = chuan_hoa_kich_thuoc(320, 240, canh_toi_da=1536)

        assert w <= 320 + BOI_SO and h <= 240 + BOI_SO

    def test_ep_ty_le_qua_dai_ve_2_1(self):
        """Trên 2:1 model bám mask kém hẳn."""
        w, h = chuan_hoa_kich_thuoc(3000, 500, canh_toi_da=1536)

        assert w / h <= 2.0 + 0.01

    def test_anh_doc_cung_bi_ep(self):
        w, h = chuan_hoa_kich_thuoc(500, 3000, canh_toi_da=1536)

        assert h / w <= 2.0 + 0.01

    def test_kich_thuoc_vo_ly_thi_bao_loi_ngay(self):
        with pytest.raises(ValueError):
            chuan_hoa_kich_thuoc(0, 100, canh_toi_da=1536)


# ---------- Vùng ----------


class TestVung:
    def test_doi_he_toa_do_theo_ty_le(self):
        vung = Vung(100, 50, 200, 150).theo_ty_le((400, 300), (200, 150))

        assert vung.as_tuple() == (50, 25, 100, 75)

    def test_noi_rong_khong_vuot_bien(self):
        vung = Vung(2, 2, 50, 50).noi_rong(10, (100, 100))

        assert vung.as_tuple() == (0, 0, 60, 60)

    def test_khung_rong_la_khong_hop_le(self):
        assert not Vung(10, 10, 10, 40).hop_le
        assert not Vung(40, 10, 10, 40).hop_le
        assert Vung(10, 10, 40, 40).hop_le


# ---------- Mask gửi API ----------


class TestDungMask:
    def test_vung_sua_la_trong_suot_phan_con_lai_duc(self):
        """Quy ước OpenAI ngược trực giác: alpha = 0 mới là chỗ được sửa."""
        mask = Image.open(__import__("io").BytesIO(dung_mask((100, 100), Vung(20, 20, 60, 60))))

        assert mask.getpixel((40, 40))[3] == 0  # trong khung -> sua
        assert mask.getpixel((5, 5))[3] == 255  # ngoai khung -> giu

    def test_cung_kich_thuoc_voi_anh_gui_len(self):
        """API từ chối mask lệch kích thước."""
        mask = Image.open(__import__("io").BytesIO(dung_mask((208, 144), Vung(10, 10, 50, 50))))

        assert mask.size == (208, 144)

    def test_khung_khong_hop_le_thi_mask_duc_hoan_toan(self):
        mask = Image.open(__import__("io").BytesIO(dung_mask((60, 60), Vung(30, 30, 30, 30))))

        assert mask.getpixel((30, 30))[3] == 255


# ---------- Ghép đè: chốt bảo đảm ----------


class TestGhepDe:
    def test_ngoai_khung_giu_nguyen_tung_pixel(self):
        """Bài test quan trọng nhất của cả tính năng.

        Model trả về một ảnh xanh hoàn toàn — tức nó đã vẽ lại sạch cả khung.
        Sau khi ghép, mọi góc ảnh vẫn phải đỏ y như gốc.
        """
        ket_qua = ghep_de(_anh(DO), _anh(XANH), Vung(80, 40, 120, 60))

        for diem in [(0, 0), (199, 0), (0, 99), (199, 99), (5, 50), (195, 50)]:
            assert ket_qua.getpixel(diem) == DO, f"pixel {diem} bi doi ngoai vung sua"

    def test_trong_khung_lay_anh_moi(self):
        ket_qua = ghep_de(_anh(DO), _anh(XANH), Vung(80, 40, 120, 60))

        assert ket_qua.getpixel((100, 50)) == XANH

    def test_tu_resize_khi_model_tra_ve_kich_thuoc_khac(self):
        """Model trả ảnh ở kích thước đã làm tròn bội số 16, khác ảnh gốc."""
        ket_qua = ghep_de(_anh(DO, (200, 100)), _anh(XANH, (208, 96)), Vung(80, 40, 120, 60))

        assert ket_qua.size == (200, 100)
        assert ket_qua.getpixel((100, 50)) == XANH
        assert ket_qua.getpixel((0, 0)) == DO

    def test_khung_khong_hop_le_thi_tra_lai_anh_goc(self):
        """Không khoanh được vùng thì thà không đổi gì, hơn là vẽ lại cả ảnh."""
        ket_qua = ghep_de(_anh(DO), _anh(XANH), Vung(50, 50, 50, 50))

        assert ket_qua.getpixel((100, 50)) == DO

    def test_khong_lam_hong_anh_goc(self):
        goc = _anh(DO)

        ghep_de(goc, _anh(XANH), Vung(80, 40, 120, 60))

        assert goc.getpixel((100, 50)) == DO

    def test_vien_mem_tao_dai_chuyen_tiep_thay_vi_duong_cat(self):
        vung = Vung(40, 20, 160, 80)
        muot = ghep_de(_anh(DO), _anh(XANH), vung, vien_mem=8)
        sac = ghep_de(_anh(DO), _anh(XANH), vung, vien_mem=0)

        assert _so_pixel_pha(muot) > 0, "phai co dai chuyen tiep"
        assert _so_pixel_pha(sac) == 0, "vien_mem=0 phai cat sac"

    def test_vung_nho_van_an_mau_du_dam_o_giua(self):
        """Lỗi thật đã gặp: viền mềm ăn vào giữa khung nhỏ, thay đổi bị nhợt."""
        for cao in (12, 20, 40):
            vung = Vung(80, 50 - cao // 2, 120, 50 + cao // 2)

            ket_qua = ghep_de(_anh(DO), _anh(XANH), vung, vien_mem=8)

            assert ket_qua.getpixel((100, 50)) == XANH, f"vung cao {cao} bi pha loang o giua"


# ---------- Đóng nhãn ----------


class TestDongNhan:
    def test_giu_nguyen_kich_thuoc(self):
        ket_qua = dong_nhan(_anh(DO, (400, 300)), "Ảnh minh hoạ do AI tạo")

        assert ket_qua.size == (400, 300)

    def test_nhan_nam_o_goc_duoi_phai(self):
        ket_qua = dong_nhan(_anh(DO, (400, 300)), "Ảnh minh hoạ do AI tạo")

        assert ket_qua.getpixel((390, 290)) != DO  # goc duoi phai da bi de nhan
        assert ket_qua.getpixel((10, 10)) == DO  # goc tren trai con nguyen

    def test_chu_tieng_viet_co_dau_khong_lam_no(self):
        """Nhãn là chốt an toàn — thiếu font cũng không được ném lỗi."""
        assert dong_nhan(_anh(DO, (320, 240)), "Ảnh minh hoạ do AI tạo — không phải hiện trạng")


# ---------- Đọc / xuất ----------


class TestDocXuat:
    def test_vong_tron_doc_xuat_giu_nguyen_anh(self):
        anh = doc_anh(xuat_png(_anh(DO, (64, 48))))

        assert anh.size == (64, 48)
        assert anh.mode == "RGB"
        assert anh.getpixel((10, 10)) == DO

    def test_anh_co_alpha_duoc_ep_ve_rgb(self):
        """gpt-image-2 từ chối nền trong suốt."""
        import io

        bo_dem = io.BytesIO()
        Image.new("RGBA", (32, 32), (255, 0, 0, 0)).save(bo_dem, format="PNG")

        assert doc_anh(bo_dem.getvalue()).mode == "RGB"
