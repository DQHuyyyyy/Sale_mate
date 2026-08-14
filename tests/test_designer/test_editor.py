"""Test bộ điều phối sửa ảnh — dùng bản giả, không chạm OpenAI.

Hai nhóm quan trọng nhất:

- `TestChanYeuCauMoHo`: yêu cầu không rõ thì DỪNG TRƯỚC lượt gọi sinh ảnh. Đây
  vừa là trải nghiệm (hỏi lại người dùng) vừa là chốt chi phí — hỏng chốt này
  thì mỗi câu "làm đẹp hơn đi" là một lượt sinh ảnh mất tiền đổ đi.
- `TestKhungHong`: model trả toạ độ rác là chuyện xảy ra thật. Không bắt ở đây
  thì mask sai chỗ và ảnh ra vẫn "trông hợp lý", rất khó lần ra.
"""

from __future__ import annotations

import pytest
from PIL import Image

from src.designer.editor import DOI_THUOC_TINH, NHAN, THAY_THE, THEM, XOA, ImageEditService
from src.designer.pipeline import doc_anh, xuat_png
from src.services.designer import FakeBoDinhVi, FakeImageEditor

DO = (255, 0, 0)
XANH = (0, 0, 255)


def _anh_goc(kich_thuoc: tuple[int, int] = (640, 480)) -> bytes:
    return xuat_png(Image.new("RGB", kich_thuoc, DO))


def _service(dinh_vi: str | None = None, **kwargs) -> tuple[ImageEditService, FakeBoDinhVi, FakeImageEditor]:
    """Mặc định KHÔNG mask — đúng cấu hình đang chạy thật."""
    bo_dinh_vi = FakeBoDinhVi(dinh_vi) if dinh_vi is not None else FakeBoDinhVi()
    editor = FakeImageEditor(mau=XANH)
    return ImageEditService(bo_dinh_vi, editor, **kwargs), bo_dinh_vi, editor


# ---------- Đường thành công ----------


class TestSuaThanhCong:
    @pytest.mark.asyncio
    async def test_tra_ve_anh_png_doc_duoc(self):
        service, _, _ = _service()

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm thành xanh")

        assert not ket_qua.can_hoi_them
        assert doc_anh(ket_qua.anh_png).size == (640, 480)

    @pytest.mark.asyncio
    async def test_giu_nguyen_kich_thuoc_anh_goc(self):
        """Ảnh gửi model đã bị làm tròn bội số 16 — ảnh trả về phải về đúng gốc."""
        service, _, _ = _service()

        ket_qua = await service.sua(anh_goc=_anh_goc((777, 501)), lenh="đổi màu rèm")

        assert doc_anh(ket_qua.anh_png).size == (777, 501)

    @pytest.mark.asyncio
    async def test_khong_mask_thi_lay_toan_bo_anh_model(self):
        """Chế độ mặc định. Model vẽ lại cả khung thì ta lấy cả khung.

        Đây là điều khiến kết quả bằng được ChatGPT. Bản trước dán lại pixel gốc
        ở mọi chỗ ngoài khung, nên model đã xoá xong cái quạt là ta vẽ nó trở
        lại — người dùng thấy "chưa xoá hết".
        """
        service, _, _ = _service()

        anh = doc_anh((await service.sua(anh_goc=_anh_goc(), lenh="bỏ cái quạt")).anh_png)

        assert anh.getpixel((30, 30)) == XANH, "ngoai khung cung phai lay anh model"

    @pytest.mark.asyncio
    async def test_khong_mask_thi_khong_gui_mask_len_api(self):
        service, _, editor = _service()

        await service.sua(anh_goc=_anh_goc(), lenh="bỏ cái quạt")

        assert editor.mask_cuoi is None

    @pytest.mark.asyncio
    async def test_bat_mask_thi_chi_doi_trong_khung(self):
        """Chế độ cũ vẫn giữ nguyên, chờ có bộ định vị đáng tin thì bật lại."""
        service, _, editor = _service(
            '{"ro_rang": true, "doi_tuong": "rèm", "khung": [0.6, 0.1, 0.9, 0.7]}', dung_mask=True
        )

        anh = doc_anh((await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")).anh_png)

        assert editor.mask_cuoi is not None
        assert anh.getpixel((30, 30)) == DO, "ngoai khung phai giu nguyen"
        assert anh.getpixel((480, 200)) == XANH, "trong khung phai doi"

    @pytest.mark.asyncio
    async def test_khong_mask_thi_khung_hong_khong_can_tro(self):
        """Bỏ mask là thoát hẳn phụ thuộc vào khung toạ độ — thứ chỉ đúng ~21,7%."""
        service, _, editor = _service('{"ro_rang": true, "doi_tuong": "quạt", "khung": "rác"}')

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="bỏ cái quạt")

        assert editor.so_lan_goi == 1
        assert not ket_qua.can_hoi_them

    @pytest.mark.asyncio
    async def test_dong_nhan_ai_vao_anh(self):
        service, _, _ = _service()

        anh = doc_anh((await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")).anh_png)

        assert anh.getpixel((630, 470)) != DO, "goc duoi phai phai co nhan"

    @pytest.mark.asyncio
    async def test_gui_model_dung_kich_thuoc_boi_so_16(self):
        service, _, editor = _service()

        await service.sua(anh_goc=_anh_goc((777, 501)), lenh="đổi màu rèm")

        rong, cao = (int(v) for v in editor.kich_thuoc_cuoi.split("x"))
        assert rong % 16 == 0 and cao % 16 == 0

    @pytest.mark.asyncio
    async def test_nhac_model_bam_dung_vat_the(self):
        service, _, editor = _service()

        await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm thành xanh")

        assert "rèm" in editor.lenh_cuoi
        assert "đổi màu rèm thành xanh" in editor.lenh_cuoi


# ---------- Quy tắc chống vỡ ảnh ----------


class TestQuyTacChongVoAnh:
    """Lỗi thật đã gặp: model trả về vùng trống, ảnh cuối có khối đen giữa phòng."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("thao_tac", [XOA, THAY_THE, DOI_THUOC_TINH])
    async def test_moi_thao_tac_deu_cam_mang_mau_phang(self, thao_tac: str):
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{thao_tac}", "doi_tuong": "quạt", "khung": [0.4, 0.3, 0.6, 0.7]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="bỏ cái quạt đi")

        lenh = editor.lenh_cuoi
        assert "KHÔNG để lại mảng đen" in lenh
        assert "vùng trong suốt" in lenh
        assert "trả lại ảnh gốc y nguyên" in lenh

    @pytest.mark.asyncio
    async def test_xoa_thi_duoc_phep_dung_lai_nen(self):
        """Bản trước dặn 'không thêm vật thể mới' cho mọi ca — chính câu đó làm
        model bí khi phải xoá, vì xoá cái quạt thì phải vẽ lại sàn phía sau."""
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{XOA}", "doi_tuong": "quạt", "khung": [0.4, 0.3, 0.6, 0.7]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="bỏ cái quạt đi")

        assert "dựng lại nền phía sau" in editor.lenh_cuoi
        assert "ĐƯỢC PHÉP vẽ thêm phần nền" in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_doi_thuoc_tinh_thi_cam_thay_vat_the(self):
        """Ngược với xoá: ở đây vẽ thêm là sai."""
        service, _, editor = _service()

        await service.sua(anh_goc=_anh_goc(), lenh="rèm màu xanh")

        assert "Giữ NGUYÊN vật thể" in editor.lenh_cuoi
        assert "dựng lại nền phía sau" not in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_thay_the_thi_doi_bong_tiep_dat(self):
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{THAY_THE}", "doi_tuong": "sofa", "khung": [0.2, 0.4, 0.6, 0.8]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="đổi sofa thành ghế da")

        assert "bóng tiếp đất" in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_thao_tac_la_thi_roi_ve_loai_it_pha_anh_nhat(self):
        service, _, editor = _service(
            '{"ro_rang": true, "thao_tac": "xoa_sach_can_ho", "doi_tuong": "rèm", "khung": [0.6, 0.1, 0.9, 0.7]}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="rèm xanh")

        assert "Giữ NGUYÊN vật thể" in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_thieu_thao_tac_van_chay_duoc(self):
        """Model cũ chưa biết trả `thao_tac` — không được vì thế mà hỏng."""
        service, _, editor = _service('{"ro_rang": true, "doi_tuong": "rèm", "khung": [0.6, 0.1, 0.9, 0.7]}')

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="rèm xanh")

        assert not ket_qua.can_hoi_them
        assert editor.so_lan_goi == 1


# ---------- Chốt chi phí ----------


class TestChanYeuCauMoHo:
    @pytest.mark.asyncio
    async def test_khong_goi_model_sinh_anh_khi_yeu_cau_mo_ho(self):
        """Chốt chi phí: lượt đắt không được chạy."""
        service, _, editor = _service('{"ro_rang": false, "cau_hoi": "Bạn muốn đổi màu gì?"}')

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="làm đẹp hơn đi")

        assert editor.so_lan_goi == 0
        assert ket_qua.can_hoi_them
        assert ket_qua.cau_hoi == "Bạn muốn đổi màu gì?"

    @pytest.mark.asyncio
    async def test_model_tra_rac_thi_hoi_lai_chu_khong_no(self):
        service, _, editor = _service("xin lỗi tôi không hiểu")

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="abc")

        assert editor.so_lan_goi == 0
        assert ket_qua.can_hoi_them
        assert ket_qua.cau_hoi

    @pytest.mark.asyncio
    async def test_thieu_cau_hoi_thi_dung_cau_mac_dinh(self):
        """Không bao giờ trả câu hỏi rỗng cho người dùng."""
        service, _, _ = _service('{"ro_rang": false}')

        assert (await service.sua(anh_goc=_anh_goc(), lenh="sửa đi")).cau_hoi


# ---------- Khung toạ độ hỏng ----------


class TestKhungHong:
    """Chỉ có nghĩa khi BẬT mask — tắt mask thì khung toạ độ không được dùng tới."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "khung",
        [
            "[0.1, 0.1]",  # thieu phan tu
            '"0.1,0.2,0.3,0.4"',  # chuoi thay vi mang
            "[0.5, 0.5, 0.5, 0.5]",  # khung rong
            '["a", "b", "c", "d"]',  # khong phai so
        ],
    )
    async def test_khung_khong_dung_thi_hoi_lai(self, khung: str):
        service, _, editor = _service(f'{{"ro_rang": true, "doi_tuong": "rèm", "khung": {khung}}}', dung_mask=True)

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")

        assert editor.so_lan_goi == 0
        assert ket_qua.can_hoi_them

    @pytest.mark.asyncio
    async def test_toa_do_vuot_khoang_thi_cat_ve_bien_anh(self):
        service, _, _ = _service(
            '{"ro_rang": true, "doi_tuong": "rèm", "khung": [-0.5, -0.5, 1.8, 1.8]}', dung_mask=True
        )

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")

        assert not ket_qua.can_hoi_them

    @pytest.mark.asyncio
    async def test_toa_do_dao_dau_duoi_van_dung_duoc(self):
        """Model trả x1 < x0 là chuyện xảy ra; đảo lại thay vì bỏ cuộc."""
        service, _, editor = _service(
            '{"ro_rang": true, "doi_tuong": "rèm", "khung": [0.9, 0.7, 0.6, 0.1]}', dung_mask=True
        )

        ket_qua = await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")

        assert editor.so_lan_goi == 1
        assert not ket_qua.can_hoi_them


# ---------- JSON bọc trong ``` ----------


@pytest.mark.asyncio
async def test_json_boc_trong_khoi_code_van_doc_duoc():
    """Model hay bọc ```json dù đã dặn đừng — cùng bệnh với PlanNode."""
    boc = '```json\n{"ro_rang": true, "doi_tuong": "rèm", "khung": [0.6, 0.1, 0.9, 0.7]}\n```'
    service, _, editor = _service(boc)

    await service.sua(anh_goc=_anh_goc(), lenh="đổi màu rèm")

    assert editor.so_lan_goi == 1


@pytest.mark.asyncio
async def test_nhan_la_chuoi_tieng_viet_co_dau():
    assert "AI" in NHAN


# ---------- Thao tác THÊM ----------


class TestThemVatThe:
    """Sinh ra từ lỗi thật: người dùng bảo "thêm chiếc tủ lạnh", trợ lý hỏi ngược
    "bạn muốn xoá hay thay thế ghế da?" rồi lặp vòng.

    Nguyên nhân là prompt chỉ khai ba thao tác nên model không có ô nào để xếp
    yêu cầu thêm đồ vào, chứ không phải model kém.
    """

    @pytest.mark.asyncio
    async def test_duoc_phep_dat_them_vat_the_moi(self):
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{THEM}", "doi_tuong": "tủ lạnh", "khung": [0.3, 0.4, 0.5, 0.8]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="thêm chiếc tủ lạnh 2 ngăn trước ghế da")

        assert "Đưa THÊM vật thể" in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_them_thi_cam_dong_vao_do_dac_san_co(self):
        """Thêm đồ không được phép xoá hay xê dịch thứ đang có."""
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{THEM}", "doi_tuong": "chậu cây", "khung": [0.1, 0.5, 0.3, 0.9]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="thêm chậu cây góc phòng")

        lenh = editor.lenh_cuoi
        assert "GIỮ NGUYÊN" in lenh
        assert "không xoá, không thay" in lenh

    @pytest.mark.asyncio
    async def test_them_doi_hoi_bong_tiep_dat_va_dung_ty_le(self):
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{THEM}", "doi_tuong": "tủ lạnh", "khung": [0.3, 0.4, 0.5, 0.8]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="thêm tủ lạnh")

        assert "bóng tiếp đất" in editor.lenh_cuoi
        assert "đúng tỉ lệ" in editor.lenh_cuoi

    @pytest.mark.asyncio
    async def test_khong_lan_sang_quy_tac_cua_xoa(self):
        service, _, editor = _service(
            f'{{"ro_rang": true, "thao_tac": "{THEM}", "doi_tuong": "tủ lạnh", "khung": [0.3, 0.4, 0.5, 0.8]}}'
        )

        await service.sua(anh_goc=_anh_goc(), lenh="thêm tủ lạnh")

        assert "Xoá hẳn vật thể" not in editor.lenh_cuoi
