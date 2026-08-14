"""Test proxy sửa ảnh — trọng tâm là hạn mức riêng, chặt hơn hạn mức chat.

Vì sao phải có test riêng: một lượt sửa ảnh tốn tiền gấp khoảng mười lần một
lượt chat. Nếu ai đó vô tình cho nó dùng chung `RateLimiter` với chat thì khách
đổi được 10 lượt rẻ thành 10 lượt đắt, và không có gì báo động.

Không chạm lõi AI thật: `httpx.AsyncClient` bị thay bằng bản giả.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest  # noqa: E402
from app.core.ratelimit import RateLimiter  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import designer as designer_router  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BODY = {"image_url": "https://example.test/a.png", "instruction": "đổi màu rèm"}


class _ResponseGia:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {"status": "ok", "image_base64": "QUJD", "object_edited": "rèm"}

    def json(self) -> dict:
        return self._payload


class _ClientGia:
    """Thay AsyncClient — ghi lại lời gọi, không mở kết nối nào."""

    da_goi: list[tuple[str, dict]] = []
    tra_ve = _ResponseGia()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url: str, json: dict):  # noqa: A002
        _ClientGia.da_goi.append((url, json))
        return _ClientGia.tra_ve


@pytest.fixture(autouse=True)
def _co_lap(monkeypatch: pytest.MonkeyPatch):
    """Hạn mức mới mỗi test, và không lượt gọi mạng nào thoát ra."""
    # Khớp production: hạn mức đang TẮT. Test nào cần đo cơ chế thì tự cắm
    # limiter riêng — xem TestHanMuc.
    monkeypatch.setattr(designer_router, "_gioi_han", None)
    # `chat_enabled` là property chỉ đọc suy ra từ `ai_core_url` — đặt vào trường gốc.
    monkeypatch.setattr(designer_router.settings, "ai_core_url", "http://ai-core.test")
    monkeypatch.setattr(designer_router.httpx, "AsyncClient", lambda **kwargs: _ClientGia())
    _ClientGia.da_goi = []
    _ClientGia.tra_ve = _ResponseGia()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHanMuc:
    def test_dang_tat_theo_yeu_cau_san_pham(self):
        """0 = tắt. Đặt lại số dương là bật, không phải sửa code."""
        assert designer_router.ANH_MOI_10_PHUT == 0
        assert designer_router._gioi_han is None

    def test_tat_thi_goi_bao_nhieu_lan_cung_duoc(self, client: TestClient):
        for _ in range(8):
            assert client.post("/api/image/edit", json=BODY).status_code == 200

    def test_bat_lai_thi_van_chan_dung(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Cơ chế còn nguyên, chỉ là đang tắt — giữ test để bật lại không phải viết lại."""
        monkeypatch.setattr(designer_router, "_gioi_han", RateLimiter(2, 600.0))

        for _ in range(2):
            assert client.post("/api/image/edit", json=BODY).status_code == 200
        response = client.post("/api/image/edit", json=BODY)

        assert response.status_code == 429
        assert response.headers["Retry-After"]
        assert "thử lại sau" in response.json()["detail"].lower()


class TestChuyenTiep:
    def test_goi_dung_endpoint_cua_loi_ai(self, client: TestClient):
        client.post("/api/image/edit", json=BODY)

        url, gui = _ClientGia.da_goi[0]
        assert url == "http://ai-core.test/api/v1/image/edit"
        assert gui["instruction"] == "đổi màu rèm"

    def test_tra_nguyen_ket_qua_cua_loi_ai(self, client: TestClient):
        body = client.post("/api/image/edit", json=BODY).json()

        assert body["status"] == "ok"
        assert body["image_base64"] == "QUJD"

    def test_giu_nguyen_thong_diep_het_luot_cua_loi_ai(self, client: TestClient):
        """Gộp thành câu chung là nuốt mất thông tin người dùng cần."""
        _ClientGia.tra_ve = _ResponseGia(429, {"detail": "Tính năng sửa ảnh đã hết lượt hôm nay."})

        response = client.post("/api/image/edit", json=BODY)

        assert response.status_code == 429
        assert "hết lượt hôm nay" in response.json()["detail"]

    def test_chua_cau_hinh_loi_ai_thi_503(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(designer_router.settings, "ai_core_url", "")

        assert client.post("/api/image/edit", json=BODY).status_code == 503


class TestKiemTraDauVao:
    @pytest.mark.parametrize(
        "body",
        [
            {"image_url": "", "instruction": "đổi màu rèm"},
            {"image_url": "https://a.test/x.png", "instruction": ""},
            {"instruction": "đổi màu rèm"},
        ],
    )
    def test_thieu_hoac_rong_thi_422(self, client: TestClient, body: dict):
        assert client.post("/api/image/edit", json=body).status_code == 422
