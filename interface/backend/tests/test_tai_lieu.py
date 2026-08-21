"""Kiểm thử cầu nối tài liệu — đích của nút trích nguồn.

Trích nguồn chỉ có giá trị khi bấm vào xem được. Route này là chỗ duy nhất chặn
quyền: lõi AI không có khái niệm người dùng, nên nó mở cho mọi request nội bộ.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import httpx  # noqa: E402
import pytest  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import tai_lieu as tai_lieu_router  # noqa: E402
from app.schemas.auth import CurrentUser  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SALE = CurrentUser(id=7, username="sale01", full_name="Nguyễn Văn Sale", role="sale")

_TAI_LIEU = {
    "doc_id": "knowledge:phap-ly-thu-tuc",
    "title": "Pháp lý & thủ tục sang tên",
    "section": "Pháp lý & thủ tục",
    "version": "2026-08-14",
    "so_ky_tu": 8083,
    "noi_dung": "# Pháp lý & thủ tục sang tên\n\nNội dung…",
    "source_url": "",
}


class _Client:
    """Thay `httpx.AsyncClient` — test không được gọi lõi AI thật."""

    def __init__(self, status: int = 200, body: object = None) -> None:
        self._status, self._body = status, body if body is not None else [_TAI_LIEU]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url: str):
        return httpx.Response(self._status, json=self._body, request=httpx.Request("GET", url))


def _gia_lap(monkeypatch: pytest.MonkeyPatch, **kwargs) -> None:
    monkeypatch.setattr(tai_lieu_router.httpx, "AsyncClient", lambda **_: _Client(**kwargs))


def as_user(user: CurrentUser) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _don():
    yield
    app.dependency_overrides.clear()


class TestPhanQuyen:
    def test_phai_dang_nhap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tài liệu là hồ sơ nội bộ của đội bán hàng, không mở cho khách vãng lai."""
        _gia_lap(monkeypatch)
        app.dependency_overrides.clear()

        assert TestClient(app).get("/api/tai-lieu").status_code in (401, 403)

    def test_da_dang_nhap_thi_xem_duoc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _gia_lap(monkeypatch)

        r = as_user(SALE).get("/api/tai-lieu")

        assert r.status_code == 200
        assert r.json()[0]["doc_id"] == "knowledge:phap-ly-thu-tuc"


class TestDanOng:
    def test_doc_id_co_dau_hai_cham_khong_bi_cat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`doc_id` là `knowledge:phap-ly-thu-tuc` — thiếu `:path` thì Starlette
        cắt sai và mọi nút trích nguồn dẫn tới 404."""
        _gia_lap(monkeypatch, body=_TAI_LIEU)

        r = as_user(SALE).get("/api/tai-lieu/knowledge:phap-ly-thu-tuc")

        assert r.status_code == 200
        assert r.json()["noi_dung"].startswith("# Pháp lý")

    def test_loi_ai_tra_404_thi_giu_nguyen_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _gia_lap(monkeypatch, status=404, body={"detail": "x"})

        assert as_user(SALE).get("/api/tai-lieu/knowledge:khong-co").status_code == 404

    def test_loi_ai_chet_thi_tra_502_khong_phai_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lõi AI sập không được thành lỗi 500 vô nghĩa trước mặt người dùng."""

        class _Hong(_Client):
            async def get(self, url: str):
                raise httpx.ConnectError("mất kết nối")

        monkeypatch.setattr(tai_lieu_router.httpx, "AsyncClient", lambda **_: _Hong())

        r = as_user(SALE).get("/api/tai-lieu")

        assert r.status_code == 502
        assert "thử lại" in r.json()["detail"].lower()
