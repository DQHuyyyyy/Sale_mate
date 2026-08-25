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
    class Ghi(list):
        """List các câu SQL, kèm `.params` để soi cả giá trị đã truyền."""

        params: list[object]

    ghi = Ghi()
    ghi_params: list[object] = []

    def gia_lap(sql, params=None):
        ghi.append(sql)
        ghi_params.append(params)
        return []

    monkeypatch.setattr(apartments_router, "fetch_all", gia_lap)
    monkeypatch.setattr(apartments_router, "numeric_columns_ready", lambda: True)
    ghi.params = ghi_params
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

    # So SAU KHI chuẩn hoá chứ không nguyên văn — xem TestLoaiCanKhopTienTo bên
    # dưới. Trước đây khẳng định ở đây là `"Phân khu" = %s`.
    assert '"Phân khu"' in sql_da_chay[0].split("WHERE")[-1]
    assert "Ocean Park 2" in sql_da_chay.params[0]


def test_khong_loc_phan_khu_khi_client_khong_gui(sql_da_chay: list[str]) -> None:
    TestClient(app).get("/api/apartments")

    assert "Phân khu" not in sql_da_chay[0].split("WHERE")[-1]


class TestLoaiCanKhopTienTo:
    """Loại căn phải khớp theo TIỀN TỐ, không phải bằng đúng.

    Lỗi đã xảy ra thật: hỏi "căn 2 phòng ngủ ở Ocean Park 1" thì trợ lý liệt kê
    đủ danh sách còn lưới bên trái hiện **0 căn**.

    Nguyên nhân là hai luật so khớp ngược nhau cho cùng một trường. Lõi AI trả
    `unit_type` là tiền tố "2PN" mỗi khi số phòng ngủ ứng với NHIỀU giá trị thật
    trong DB (`_match_unit_type` ở src/agents/tools/search.py), mà 2PN có tới
    hai: "2PN, 1WC" và "2PN, 2WC". Router thì so bằng đúng, nên "2pn" không bao
    giờ bằng "2pn,2wc".

    Đo trên dữ liệu thật sau khi sửa: chat 9 căn, lưới 9 căn.
    """

    def test_dung_like_tien_to_chu_khong_phai_bang_dung(self, sql_da_chay: list[str]) -> None:
        TestClient(app).get("/api/apartments", params={"type": "2PN"})

        dieu_kien = sql_da_chay[0].split("WHERE")[-1]
        assert "LIKE" in dieu_kien, "so bằng đúng thì mọi câu hỏi theo số phòng ngủ đều ra rỗng"
        assert "2PN" in sql_da_chay.params[0]

    def test_gia_tri_day_du_tu_dropdown_van_khop(self, sql_da_chay: list[str]) -> None:
        """Dropdown trên form gửi nguyên chuỗi đầy đủ, và nó là tiền tố của chính nó.

        Nếu không, sửa cho chat chạy được sẽ làm hỏng đường người dùng tự lọc.
        """
        TestClient(app).get("/api/apartments", params={"type": "2PN, 2WC"})

        assert "LIKE" in sql_da_chay[0].split("WHERE")[-1]
        assert "2PN, 2WC" in sql_da_chay.params[0]

    def test_phan_khu_so_sau_khi_chuan_hoa(self, sql_da_chay: list[str]) -> None:
        """Model có thể gửi "OceanPark 1" trong khi DB ghi "Ocean Park 1".

        Cùng luật với `inventory_search` phía lõi AI — hai bên lệch nhau là chat
        và lưới nói hai tập căn khác nhau.
        """
        TestClient(app).get("/api/apartments", params={"subdivision": "OceanPark 1"})

        dieu_kien = sql_da_chay[0].split("WHERE")[-1]
        assert "replace(lower" in dieu_kien
        assert 'a."Phân khu" = %s' not in dieu_kien, "so nguyên văn là khớp hụt khi model viết liền"


class TestLocVeSinh:
    """Số vệ sinh là bộ lọc RIÊNG, không gộp vào `type`.

    Trước đây lõi AI đọc mỗi số phòng ngủ: "2 phòng ngủ và 1 vệ sinh ở Ocean
    Park 3" cho ra 15 căn — gồm cả 9 căn 2PN-2WC — trong khi đáp án đúng là 6.
    Trợ lý nói SAI SỐ, không phải chỉ hiện thừa.

    Tách riêng vì `type` khớp theo TIỀN TỐ, nên câu "căn 2 vệ sinh" không nêu
    phòng ngủ thì không có cách nào diễn đạt bằng nó.
    """

    def test_khop_duoi_chuoi_loai_can(self, sql_da_chay: list[str]) -> None:
        """ "2PN, 1WC" chuẩn hoá thành "2pn,1wc" — số vệ sinh nằm ở ĐUÔI."""
        TestClient(app).get("/api/apartments", params={"wc": 1})

        # `%%` chứ không `%`: psycopg dùng %s làm chỗ giữ tham số nên dấu phần
        # trăm thật phải nhân đôi trong chuỗi SQL.
        assert "'%%' || %s" in sql_da_chay[0].split("WHERE")[-1]
        assert "1wc" in sql_da_chay.params[0]

    def test_ket_hop_duoc_voi_loai_can(self, sql_da_chay: list[str]) -> None:
        """Hai bộ lọc phải AND với nhau, không cái nào ghi đè cái nào."""
        TestClient(app).get("/api/apartments", params={"type": "2PN", "wc": 1})

        dieu_kien = sql_da_chay[0].split("WHERE")[-1]
        assert dieu_kien.count("LIKE") == 2
        assert "2PN" in sql_da_chay.params[0]
        assert "1wc" in sql_da_chay.params[0]

    def test_khong_gui_thi_khong_loc(self, sql_da_chay: list[str]) -> None:
        TestClient(app).get("/api/apartments", params={"type": "Studio"})

        assert "wc" not in str(sql_da_chay.params[0])
