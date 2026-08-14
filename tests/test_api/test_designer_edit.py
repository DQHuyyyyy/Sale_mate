"""Test endpoint sửa ảnh — trọng tâm là ba cái phanh chi tiêu.

Endpoint này MỞ cho khách chưa đăng nhập và mỗi lượt thành công tốn tiền thật.
Ba chốt phải luôn còn nguyên:

1. cờ `enable_image_edit` tắt thì không gọi được
2. trần ngày chặn khi đã sinh đủ số ảnh
3. lượt "hỏi lại" KHÔNG tính vào trần — nó chưa gọi model sinh ảnh, tính vào là
   tự bóp lưu lượng hợp lệ mà chẳng tiết kiệm được đồng nào

Ảnh gốc được nạp bằng hàm giả: không test nào chạm mạng.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest
from PIL import Image

from src.api.v1 import designer as designer_router
from src.core.config import Settings, get_settings
from src.core.container import container
from src.designer.editor import ImageEditService
from src.designer.pipeline import doc_anh, xuat_png
from src.main import app
from src.services.designer import FakeBoDinhVi, FakeImageEditor

URL = "https://example.test/anh.png"


def _settings(**thay_doi) -> Settings:
    mac_dinh = {
        "_env_file": None,
        "app_env": "test",
        "openai_api_key": "",
        "cors_origins": "http://localhost:3000",
        "enable_image_edit": True,
        "image_daily_limit": 5,
    }
    return Settings(**{**mac_dinh, **thay_doi})  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _dat_lai_tran_ngay():
    """Bộ đếm là biến module — không đặt lại thì test này ảnh hưởng test kia."""
    designer_router.tran_ngay = designer_router._TranNgay()
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _anh_gia(monkeypatch: pytest.MonkeyPatch):
    """Thay hàm tải ảnh — không test nào được gọi mạng."""

    async def _tai(url: str, **kwargs):  # noqa: ARG001
        return xuat_png(Image.new("RGB", (320, 240), (255, 0, 0)))

    monkeypatch.setattr(designer_router, "tai_anh", _tai)


def _bat(dinh_vi: str | None = None, **thay_doi) -> FakeImageEditor:
    """Bật tính năng và cắm bản giả vào container."""
    cai_dat = _settings(**thay_doi)
    app.dependency_overrides[get_settings] = lambda: cai_dat

    editor = FakeImageEditor(mau=(0, 0, 255))
    bo_dinh_vi = FakeBoDinhVi(dinh_vi) if dinh_vi is not None else FakeBoDinhVi()
    container.override(ImageEditService, ImageEditService(bo_dinh_vi, editor))
    return editor


def _goi(client, lenh: str = "đổi màu rèm thành xanh"):
    return client.post("/api/v1/image/edit", json={"image_url": URL, "instruction": lenh})


# ---------- Cờ bật/tắt ----------


@pytest.mark.asyncio
async def test_co_tat_thi_tra_503_kem_cach_khac_phuc(client):
    _bat(enable_image_edit=False)

    response = await _goi(client)

    assert response.status_code == 503
    assert "ENABLE_IMAGE_EDIT" in response.json()["detail"]


# ---------- Đường thành công ----------


@pytest.mark.asyncio
async def test_tra_ve_anh_base64_doc_duoc(client):
    _bat()

    response = await _goi(client)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert doc_anh(base64.b64decode(body["image_base64"])).size == (320, 240)


@pytest.mark.asyncio
async def test_bao_ten_vat_the_da_sua(client):
    _bat()

    assert (await _goi(client)).json()["object_edited"] == "rèm"


# ---------- Hỏi lại ----------


@pytest.mark.asyncio
async def test_yeu_cau_mo_ho_thi_hoi_lai_khong_sinh_anh(client):
    editor = _bat('{"ro_rang": false, "cau_hoi": "Bạn muốn đổi màu gì?"}')

    body = (await _goi(client, "làm đẹp hơn đi")).json()

    assert body["status"] == "clarify"
    assert body["question"] == "Bạn muốn đổi màu gì?"
    assert body["image_base64"] == ""
    assert editor.so_lan_goi == 0


@pytest.mark.asyncio
async def test_hoi_lai_khong_tinh_vao_tran_ngay(client):
    """Chưa tốn tiền thì không được trừ lượt."""
    _bat('{"ro_rang": false, "cau_hoi": "Đổi màu gì?"}', image_daily_limit=1)

    for _ in range(3):
        assert (await _goi(client)).status_code == 200

    # Trần vẫn còn nguyên: một lượt rõ ràng vẫn phải chạy được.
    _bat(image_daily_limit=1)
    assert (await _goi(client)).status_code == 200


# ---------- Trần ngày ----------


@pytest.mark.asyncio
async def test_cham_tran_ngay_thi_tra_429_co_noi_dung(client):
    _bat(image_daily_limit=2)

    for _ in range(2):
        assert (await _goi(client)).status_code == 200

    response = await _goi(client)

    assert response.status_code == 429
    assert "hết lượt hôm nay" in response.json()["detail"]
    assert response.headers["Retry-After"]


@pytest.mark.asyncio
async def test_tran_bang_khong_la_khong_gioi_han(client):
    """0 = KHÔNG GIỚI HẠN, không phải chặn hết.

    Công tắc chặn là `ENABLE_IMAGE_EDIT`, còn đây là cái van. Lẫn hai thứ này
    thì đặt trần 0 với ý "bỏ giới hạn" lại thành khoá sạch tính năng.
    """
    _bat(image_daily_limit=0)

    for _ in range(5):
        assert (await _goi(client)).status_code == 200


# ---------- Kiểm tra đầu vào ----------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"image_url": "", "instruction": "đổi màu rèm"},
        {"image_url": URL, "instruction": ""},
        {"image_url": URL},
        {"instruction": "đổi màu rèm"},
    ],
)
async def test_thieu_hoac_rong_thi_422(client, body: dict):
    _bat()

    assert (await client.post("/api/v1/image/edit", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_lenh_qua_dai_bi_tu_choi(client):
    _bat()

    response = await client.post("/api/v1/image/edit", json={"image_url": URL, "instruction": "x" * 501})

    assert response.status_code == 422


# ---------- Sửa nối tiếp: ảnh nguồn đi bằng base64 ----------


def _anh_base64(kich_thuoc: tuple[int, int] = (320, 240)) -> str:
    return base64.b64encode(xuat_png(Image.new("RGB", kich_thuoc, (180, 170, 160)))).decode()


@pytest.mark.asyncio
async def test_nhan_anh_nguon_dang_base64(client):
    """Lượt sửa TIẾP: nguồn là ảnh vừa chỉnh, chưa lưu ở đâu nên không có URL."""
    _bat()

    response = await client.post(
        "/api/v1/image/edit",
        json={"image_base64": _anh_base64(), "instruction": "rèm sáng hơn"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_khong_tai_url_khi_da_co_base64(client):
    """Có ảnh sẵn rồi thì không được đi tải mạng lần nữa."""
    _bat()

    async def _no(*args, **kwargs):
        raise AssertionError("khong duoc tai anh tu URL khi da co base64")

    with patch("src.api.v1.designer.tai_anh", _no):
        response = await client.post(
            "/api/v1/image/edit",
            json={"image_base64": _anh_base64(), "instruction": "rèm sáng hơn"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"instruction": "x"},  # khong co nguon nao
        {"image_url": URL, "image_base64": "abc", "instruction": "x"},  # ca hai
    ],
)
async def test_phai_dung_mot_nguon_anh(client, body: dict):
    _bat()

    assert (await client.post("/api/v1/image/edit", json=body)).status_code == 422


@pytest.mark.asyncio
async def test_base64_hong_thi_bao_ro_thay_vi_no(client):
    _bat()

    response = await client.post(
        "/api/v1/image/edit",
        json={"image_base64": "khong-phai-base64!!!", "instruction": "rèm sáng hơn"},
    )

    assert response.status_code == 400
    assert "không đọc được" in response.json()["detail"]


@pytest.mark.asyncio
async def test_anh_qua_lon_bi_tu_choi(client):
    """Endpoint mở cho khách chưa đăng nhập — không được nhận ảnh cỡ nào cũng được."""
    _bat()

    qua_lon = base64.b64encode(b"\x00" * (13 * 1024 * 1024)).decode()

    response = await client.post(
        "/api/v1/image/edit",
        json={"image_base64": qua_lon, "instruction": "rèm sáng hơn"},
    )

    assert response.status_code == 413
