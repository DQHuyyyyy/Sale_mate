"""Kiểm thử bộ lọc giá của /api/apartments.

Không chạm database: bắt lấy SQL mà router sinh ra rồi soi toán tử. Điều đáng
kiểm ở đây là `<` hay `<=` — một ký tự quyết định lưới hiện 21 căn hay 25.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import apartments as apartments_router  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def sql_da_chay(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ghi: list[str] = []

    def gia_lap(sql, params=None):  # noqa: ARG001
        ghi.append(sql)
        return []

    monkeypatch.setattr(apartments_router, "fetch_all", gia_lap)
    monkeypatch.setattr(apartments_router, "numeric_columns_ready", lambda: True)
    return ghi


def test_mac_dinh_tinh_ca_bien(sql_da_chay: list[str]) -> None:
    """Ô "Đến" trên form là một KHOẢNG nên tính cả biên."""
    TestClient(app).get("/api/apartments", params={"price_max": 3})

    assert "a.gia_tri <= %s" in sql_da_chay[0]


def test_co_co_nghiem_ngat_thi_loai_can_dung_bien(sql_da_chay: list[str]) -> None:
    """Trợ lý S bật cờ này cho câu "dưới 3 tỷ".

    Thiếu nó thì chat đếm 21 căn còn lưới bên trái hiện 25, người dùng thấy
    ngay hai con số vênh nhau và mất tin vào cả hai.
    """
    TestClient(app).get("/api/apartments", params={"price_max": 3, "price_max_exclusive": "true"})

    assert "a.gia_tri < %s" in sql_da_chay[0]
    assert "a.gia_tri <= %s" not in sql_da_chay[0]


def test_can_duoi_khong_bi_anh_huong(sql_da_chay: list[str]) -> None:
    """Cờ chỉ tác động tới cận TRÊN, đừng làm rơi mất cận dưới."""
    TestClient(app).get(
        "/api/apartments",
        params={"price_min": 2, "price_max": 3, "price_max_exclusive": "true"},
    )

    assert "a.gia_tri >= %s" in sql_da_chay[0]
    assert "a.gia_tri < %s" in sql_da_chay[0]


def test_loc_theo_phan_khu(sql_da_chay: list[str]) -> None:
    """Trợ lý S đẩy bộ lọc này lên URL sau khi trả lời "4 căn ở Ocean Park 2
    dưới 3 tỷ" — thiếu nó thì lưới bên trái vẫn hiện 21 căn."""
    TestClient(app).get("/api/apartments", params={"subdivision": "Ocean Park 2"})

    assert '"Phân khu" = %s' in sql_da_chay[0]


def test_khong_loc_phan_khu_khi_client_khong_gui(sql_da_chay: list[str]) -> None:
    TestClient(app).get("/api/apartments")

    assert "Phân khu" not in sql_da_chay[0].split("WHERE")[-1]
