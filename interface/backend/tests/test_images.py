"""Kiểm thử endpoint sinh ảnh — tính năng "Modify Object".

Không gọi Gemini thật và không chạm database: cả hai đều bị thay bằng hàm giả.
Trọng tâm là những chỗ SAI thì nguy hiểm — nhận URL từ client (SSRF), đọc được
ảnh của căn khác, và thông điệp lỗi khi Google chưa cấp hạn mức sinh ảnh.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import asyncio  # noqa: E402
import base64  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import images as images_router  # noqa: E402
from app.services import image_edit  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BODY = {"ma_can": "VOP398", "image_id": 1, "yeu_cau": "đổi sofa thành màu nâu"}


@pytest.fixture(autouse=True)
def _moi_truong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neo cấu hình tường minh: `.env` của máy dev đổi được nhà cung cấp và tắt
    hạn mức, test không được đổi kết quả theo từng máy."""
    monkeypatch.setattr(images_router.settings, "chat_rate_limit_enabled", False)
    monkeypatch.setattr(image_edit.settings, "image_provider", "openai")
    monkeypatch.setattr(image_edit.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(image_edit.settings, "google_api_key", "test-key")


def _client() -> TestClient:
    return TestClient(app)


# ---------- Đường chạy được ----------


def test_tra_ve_data_uri_khong_luu_o_dau(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ảnh AI KHÔNG được lưu: để lẫn vào ảnh thật là quảng cáo sai sự thật."""

    async def gia_lap(ma_can, image_id, yeu_cau):  # noqa: ARG001
        return b"\x89PNG-gia", "image/png"

    monkeypatch.setattr(images_router, "sua_anh_can", gia_lap)

    response = _client().post("/api/images/modify", json=BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["anh"].startswith("data:image/png;base64,")
    assert data["la_anh_ai"] is True


# ---------- Chỗ sai thì nguy hiểm ----------


def test_khong_nhan_url_anh_tu_client() -> None:
    """Nhận URL từ client là mở đường cho người lạ bắt server tải về bất cứ thứ
    gì (SSRF). Server phải tự tra URL từ `apartment_images`."""
    assert "image_url" not in images_router.ModifyImageRequest.model_fields
    assert "url" not in images_router.ModifyImageRequest.model_fields


def test_anh_khong_thuoc_can_thi_tu_choi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Thiếu ràng buộc `ma_can` thì ai cũng đọc được ảnh của mọi căn bằng cách dò id."""
    ghi: dict = {}

    def fetch_one_gia(sql, params):
        ghi["sql"], ghi["params"] = sql, params
        return None  # không có dòng nào khớp cả id lẫn ma_can

    monkeypatch.setattr(image_edit, "fetch_one", fetch_one_gia)

    response = _client().post("/api/images/modify", json=BODY)

    assert response.status_code == 502
    assert "không tìm thấy ảnh này" in response.json()["detail"].lower()
    # Câu SQL phải ràng CẢ HAI, không chỉ id.
    assert "ma_can" in ghi["sql"] and ghi["params"] == (1, "VOP398")


@pytest.mark.parametrize(
    ("provider", "khoa_key", "ten_bien"),
    [("openai", "openai_api_key", "OPENAI_API_KEY"), ("gemini", "google_api_key", "GOOGLE_API_KEY")],
)
def test_thieu_key_thi_bao_dung_ten_bien(
    monkeypatch: pytest.MonkeyPatch, provider: str, khoa_key: str, ten_bien: str
) -> None:
    """Báo nhầm tên biến thì người dùng đi điền sai chỗ."""
    monkeypatch.setattr(image_edit.settings, "image_provider", provider)
    monkeypatch.setattr(image_edit.settings, khoa_key, "")

    response = _client().post("/api/images/modify", json=BODY)

    assert response.status_code == 502
    assert ten_bien in response.json()["detail"]


def test_han_muc_chan_khi_bat(monkeypatch: pytest.MonkeyPatch) -> None:
    async def gia_lap(ma_can, image_id, yeu_cau):  # noqa: ARG001
        return b"anh", "image/png"

    monkeypatch.setattr(images_router, "sua_anh_can", gia_lap)
    monkeypatch.setattr(images_router.settings, "chat_rate_limit_enabled", True)
    images_router._gioi_han_khach._hits.clear()

    client = _client()
    for lan in range(images_router.KHACH_MOI_10_PHUT):
        assert client.post("/api/images/modify", json=BODY).status_code == 200, lan

    response = client.post("/api/images/modify", json=BODY)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


@pytest.mark.parametrize(
    "body",
    [
        {"ma_can": "", "image_id": 1, "yeu_cau": "đổi sofa"},
        {"ma_can": "VOP398", "image_id": 0, "yeu_cau": "đổi sofa"},
        {"ma_can": "VOP398", "image_id": 1, "yeu_cau": "a"},
        {"ma_can": "VOP398", "image_id": 1},
    ],
)
def test_tham_so_thieu_hoac_sai_thi_422(body: dict) -> None:
    assert _client().post("/api/images/modify", json=body).status_code == 422


# ---------- Thông điệp lỗi phải nói được cách khắc phục ----------


def test_het_han_muc_google_thi_chi_ro_can_bat_billing() -> None:
    """Ca đã gặp thật: key hợp lệ, model văn bản gọi được, nhưng MỌI model sinh
    ảnh trả `limit: 0` vì gói free không cấp hạn mức cho chúng."""
    than = '{"error":{"message":"Quota exceeded ... limit: 0, model: gemini-3.1-flash-image"}}'

    thong_diep = image_edit._loi_tu_status(429, than)

    assert "billing" in thong_diep.lower()


@pytest.mark.parametrize(
    ("provider", "ten_bien"),
    [("openai", "OPENAI_IMAGE_MODEL"), ("gemini", "GEMINI_IMAGE_MODEL")],
)
def test_model_khong_ton_tai_thi_neu_ten_bien_moi_truong(
    monkeypatch: pytest.MonkeyPatch, provider: str, ten_bien: str
) -> None:
    monkeypatch.setattr(image_edit.settings, "image_provider", provider)

    assert ten_bien in image_edit._loi_tu_status(404, "")


def test_gemini_tra_chu_thay_vi_anh_thi_hien_nguyen_van() -> None:
    """Model nhiều khi giải thích vì sao nó không sửa — câu đó hữu ích hơn một
    thông điệp lỗi chung chung."""
    data = {"candidates": [{"content": {"parts": [{"text": "Ảnh này không có sofa nào."}]}}]}

    with pytest.raises(image_edit.ImageEditError, match="không có sofa"):
        image_edit._doc_anh_tra_ve(data)


def test_doc_duoc_ca_hai_kieu_dat_ten_khoa() -> None:
    """API trả `inlineData` nhưng tài liệu ghi `inline_data` — đọc cả hai để
    không phụ thuộc vào việc Google giữ nguyên kiểu đặt tên."""
    for khoa in ("inlineData", "inline_data"):
        data = {"candidates": [{"content": {"parts": [{khoa: {"data": "YWJj", "mimeType": "image/png"}}]}}]}

        anh, mime = image_edit._doc_anh_tra_ve(data)

        assert anh == b"abc"
        assert mime == "image/png"


# ---------- Chọn nhà cung cấp bằng biến môi trường ----------


def test_doc_anh_openai() -> None:
    """Endpoint /v1/images/edits trả b64_json, luôn là PNG."""
    anh, mime = image_edit._doc_anh_openai({"data": [{"b64_json": "YWJj"}]})

    assert anh == b"abc"
    assert mime == "image/png"


def test_openai_khong_tra_anh_thi_bao_loi() -> None:
    with pytest.raises(image_edit.ImageEditError):
        image_edit._doc_anh_openai({"data": []})


@pytest.mark.asyncio
async def test_goi_dung_nha_cung_cap_theo_cau_hinh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đổi IMAGE_PROVIDER phải đổi thật đường gọi, không chỉ đổi thông điệp lỗi."""
    da_goi: list[str] = []

    async def gia_openai(goc, mime, yeu_cau):  # noqa: ARG001
        da_goi.append("openai")
        return httpx.Response(200, json={"data": [{"b64_json": "YWJj"}]})

    async def gia_gemini(goc, mime, yeu_cau):  # noqa: ARG001
        da_goi.append("gemini")
        parts = [{"inlineData": {"data": "YWJj", "mimeType": "image/png"}}]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": parts}}]})

    monkeypatch.setattr(image_edit, "_goi_openai", gia_openai)
    monkeypatch.setattr(image_edit, "_goi_gemini", gia_gemini)
    monkeypatch.setattr(image_edit, "_anh_cua_can", lambda ma_can, image_id: "http://vi-du/anh.jpg")

    async def tai_gia(url):  # noqa: ARG001
        return b"anh-goc", "image/jpeg"

    monkeypatch.setattr(image_edit, "_tai_anh", tai_gia)

    for provider in ("openai", "gemini"):
        monkeypatch.setattr(image_edit.settings, "image_provider", provider)
        anh, _ = await image_edit.sua_anh_can("VOP398", 1, "đổi sofa")
        assert anh == b"abc"

    assert da_goi == ["openai", "gemini"]


class TestSeedream:
    """Seedream 4.0 qua BytePlus ModelArk — nhà cung cấp thứ ba.

    Đổi nhà cung cấp KHÔNG được đổi hành vi: vẫn sửa ảnh có sẵn của căn, vẫn
    trả bytes, vẫn không lưu ở đâu.
    """

    @pytest.fixture
    def _seedream(self, monkeypatch: pytest.MonkeyPatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "image_provider", "seedream")
        monkeypatch.setattr(settings, "ark_api_key", "ark-test")

    def test_gui_anh_goc_de_SUA_khong_phai_ve_tu_chu(self, _seedream) -> None:
        """Chốt chặn quan trọng nhất. Endpoint tên là `images/generations`, và
        thiếu trường `image` thì nó vẽ một căn hộ tưởng tượng thay vì sửa ảnh
        của căn — không lỗi nào báo, chỉ khách nhận nhầm ảnh."""
        from app.services import image_edit

        thu = {}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None, **k):
                thu.update(url=url, headers=headers or {}, body=json or {})
                return httpx.Response(200, json={"data": [{"b64_json": ""}]})

        monkey = pytest.MonkeyPatch()
        monkey.setattr(image_edit.httpx, "AsyncClient", lambda **_: _Client())
        asyncio.run(image_edit._goi_seedream(b"\xff\xd8\xff", "image/jpeg", "đổi sofa thành nâu"))
        monkey.undo()

        assert "image" in thu["body"], "thiếu `image` là tính năng đổi nghĩa hoàn toàn"
        assert thu["body"]["image"].startswith("data:image/jpeg;base64,")
        # Trả bytes cho phiên chat, không đi qua CDN có hạn 7 ngày.
        assert thu["body"]["response_format"] == "b64_json"
        assert thu["body"]["sequential_image_generation"] == "disabled"
        assert thu["headers"]["Authorization"] == "Bearer ark-test"

    def test_doc_anh_tra_ve_jpeg(self) -> None:
        """Đo thật: Seedream trả JPEG, không phải PNG như OpenAI."""
        from app.services.image_edit import _doc_anh_seedream

        raw, mime = _doc_anh_seedream({"data": [{"b64_json": base64.b64encode(b"\xff\xd8\xff\xe0").decode()}]})

        assert raw == b"\xff\xd8\xff\xe0"
        assert mime == "image/jpeg"

    def test_khong_co_anh_thi_bao_ro(self) -> None:
        from app.services.image_edit import ImageEditError, _doc_anh_seedream

        with pytest.raises(ImageEditError):
            _doc_anh_seedream({"data": [{}]})

    def test_thieu_key_thi_bao_dung_ten_bien(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Báo `OPENAI_API_KEY` trong khi đang chạy seedream là chỉ sai chỗ."""
        from app.core.config import settings
        from app.services.image_edit import ImageEditError, sua_anh_can

        monkeypatch.setattr(settings, "image_provider", "seedream")
        monkeypatch.setattr(settings, "ark_api_key", "")

        with pytest.raises(ImageEditError, match="ARK_API_KEY"):
            asyncio.run(sua_anh_can("VOP001", 1, "đổi sofa"))
