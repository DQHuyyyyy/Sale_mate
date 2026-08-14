"""Test hai chốt chống trả về ảnh hỏng và chống nói sai.

Cả hai đều sinh ra từ lỗi đã xảy ra thật với người dùng:

- Model trả vùng trong suốt, `.convert("RGB")` biến thành ĐEN THUẦN, ảnh cuối
  có một khối đen giữa phòng khách.
- Trợ lý vẫn báo "Mình đã chỉnh quạt theo yêu cầu" trong khi cái quạt còn
  nguyên. Khẳng định sai là vi phạm nguyên tắc số 1 của dự án.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.designer.editor import HONG_ANH, KHONG_DOI_DUOC, ImageEditService
from src.designer.pipeline import doc_anh, doc_anh_tren_nen, ty_le_be_phang, ty_le_doi, xuat_png
from src.services.designer import FakeBoDinhVi, FakeImageEditor

PHONG = (180, 170, 160)


def _phong(kich_thuoc: tuple[int, int] = (240, 180)) -> Image.Image:
    """Ảnh nền có chút vân để không phải một màu phẳng tuyệt đối."""
    anh = Image.new("RGB", kich_thuoc, PHONG)
    for x in range(0, kich_thuoc[0], 8):
        for y in range(kich_thuoc[1]):
            anh.putpixel((x, y), (190, 180, 170))
    return anh


# ---------- Trong suốt không được thành đen ----------


class TestTrongSuot:
    def test_lo_trong_suot_lay_lai_pixel_goc(self):
        goc = _phong()
        moi = Image.new("RGBA", goc.size, (60, 110, 200, 255))
        moi.paste(Image.new("RGBA", (40, 60), (0, 0, 0, 0)), (100, 60))
        bo_dem = io.BytesIO()
        moi.save(bo_dem, format="PNG")

        ket_qua = doc_anh_tren_nen(bo_dem.getvalue(), goc)

        assert ket_qua.getpixel((120, 90)) == goc.getpixel((120, 90)), "lo phai lay lai anh goc"
        assert ket_qua.getpixel((10, 10)) == (60, 110, 200), "ngoai lo van lay anh model"

    def test_anh_khong_alpha_thi_giu_nguyen(self):
        goc = _phong()
        moi = xuat_png(Image.new("RGB", goc.size, (60, 110, 200)))

        assert doc_anh_tren_nen(moi, goc).getpixel((10, 10)) == (60, 110, 200)

    def test_khac_kich_thuoc_van_lot_nen_dung(self):
        goc = _phong((240, 180))
        moi = Image.new("RGBA", (256, 176), (0, 0, 0, 0))
        bo_dem = io.BytesIO()
        moi.save(bo_dem, format="PNG")

        ket_qua = doc_anh_tren_nen(bo_dem.getvalue(), goc)

        assert ket_qua.size == (256, 176)
        assert ket_qua.getpixel((10, 10)) != (0, 0, 0), "khong duoc ra den"


# ---------- Đo mức thay đổi ----------


class TestDoThayDoi:
    def test_anh_y_het_thi_ty_le_doi_bang_khong(self):
        goc = _phong()

        assert ty_le_doi(goc, goc.copy()) == 0.0

    def test_ve_lai_toan_bo_thi_ty_le_doi_gan_mot(self):
        goc = _phong()
        moi = Image.new("RGB", goc.size, (20, 200, 20))

        assert ty_le_doi(goc, moi) > 0.95

    def test_bo_qua_sai_khac_li_ti_do_nen_lai(self):
        """Lệch vài đơn vị màu là do PNG/resize, không phải người dùng nhìn thấy."""
        goc = _phong()
        moi = doc_anh(xuat_png(goc)).point(lambda v: min(255, v + 3))

        assert ty_le_doi(goc, moi) < 0.01

    def test_doi_mot_goc_nho_thi_ty_le_nho_nhung_khac_khong(self):
        goc = _phong()
        moi = goc.copy()
        moi.paste(Image.new("RGB", (40, 30), (20, 200, 20)), (100, 60))

        ty_le = ty_le_doi(goc, moi)
        assert 0.02 < ty_le < 0.06


class TestDoBePhang:
    def test_khoi_den_moi_bi_bat(self):
        goc = _phong()
        moi = goc.copy()
        moi.paste(Image.new("RGB", (60, 60), (0, 0, 0)), (80, 60))

        assert ty_le_be_phang(goc, moi) > 0.05

    def test_anh_binh_thuong_thi_gan_bang_khong(self):
        goc = _phong()
        moi = Image.new("RGB", goc.size, (90, 100, 110))

        assert ty_le_be_phang(goc, moi) < 0.01

    def test_vung_von_da_toi_khong_bi_tinh_la_hong(self):
        """Ảnh phòng ngủ ban đêm vốn có mảng rất tối — đếm cả chúng là báo động giả."""
        goc = _phong()
        goc.paste(Image.new("RGB", (80, 80), (0, 0, 0)), (10, 10))
        moi = goc.copy()

        assert ty_le_be_phang(goc, moi) == 0.0


# ---------- Chốt trong bộ điều phối ----------


def _service(mau: tuple[int, int, int]) -> ImageEditService:
    return ImageEditService(FakeBoDinhVi(), FakeImageEditor(mau=mau))


class TestChotTrongEditor:
    @pytest.mark.asyncio
    async def test_anh_khong_doi_thi_bao_that_khong_nhan_bua(self):
        """Model trả y nguyên ảnh gốc — tuyệt đối không được nói 'đã chỉnh xong'."""
        goc = _phong()
        service = _service(PHONG)  # ban gia tra ve dung mau nen

        ket_qua = await service.sua(anh_goc=xuat_png(goc), lenh="bỏ cái quạt")

        assert ket_qua.can_hoi_them
        assert ket_qua.cau_hoi == KHONG_DOI_DUOC

    @pytest.mark.asyncio
    async def test_anh_bi_to_den_thi_khong_dua_ra(self):
        goc = _phong()
        service = _service((0, 0, 0))

        ket_qua = await service.sua(anh_goc=xuat_png(goc), lenh="bỏ cái quạt")

        assert ket_qua.can_hoi_them
        assert ket_qua.cau_hoi == HONG_ANH

    @pytest.mark.asyncio
    async def test_anh_bi_to_trang_cung_bi_chan(self):
        goc = _phong()
        service = _service((255, 255, 255))

        assert (await service.sua(anh_goc=xuat_png(goc), lenh="bỏ cái quạt")).cau_hoi == HONG_ANH

    @pytest.mark.asyncio
    async def test_anh_sua_that_thi_van_di_qua(self):
        goc = _phong()
        service = _service((60, 110, 200))

        ket_qua = await service.sua(anh_goc=xuat_png(goc), lenh="bỏ cái quạt")

        assert not ket_qua.can_hoi_them
        assert ket_qua.anh_png

    @pytest.mark.asyncio
    async def test_nhan_dong_sau_khi_kiem_tra(self):
        """Nhãn có nền tối — kiểm tra trước khi đóng, không thì tự báo động giả."""
        goc = _phong()
        service = _service((60, 110, 200))

        anh = doc_anh((await service.sua(anh_goc=xuat_png(goc), lenh="bỏ quạt")).anh_png)

        assert anh.getpixel((235, 175)) != (60, 110, 200), "goc duoi phai co nhan"
