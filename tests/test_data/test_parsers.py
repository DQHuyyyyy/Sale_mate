"""Test chuẩn hoá dữ liệu thô.

Mọi giá trị đầu vào ở đây đều lấy từ file crawl thật (Data_crawl/Data .xlsx),
không phải ví dụ bịa ra.
"""

from __future__ import annotations

import pytest

from src.data.parsers import (
    clean_text,
    format_price_label,
    normalize_layout_label,
    parse_area_m2,
    parse_directions,
    parse_int,
    parse_layout,
    parse_price_vnd,
)

# ---------------------------------------------------------------- Giá


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3,1 tỷ", 3_100_000_000),
        ("1,8 tỷ", 1_800_000_000),
        ("2 tỷ", 2_000_000_000),
        ("2,120 tỷ", 2_120_000_000),
        ("2,550 tỷ", 2_550_000_000),
        ("800 triệu", 800_000_000),
        ("3.1 tỷ", 3_100_000_000),
        (" 2,25 tỷ ", 2_250_000_000),
    ],
)
def test_parse_gia(raw, expected):
    assert parse_price_vnd(raw) == expected


def test_dau_phay_la_dau_thap_phan_khong_phai_phan_cach_nghin():
    """'2,120 tỷ' là 2,12 tỷ — không phải 2120 tỷ."""
    assert parse_price_vnd("2,120 tỷ") == 2_120_000_000


@pytest.mark.parametrize("raw", [None, "", "liên hệ", "thương lượng"])
def test_gia_khong_doc_duoc_thi_tra_none(raw):
    assert parse_price_vnd(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (3.55, 3_550_000_000),  # căn VOP954 — Excel tự đổi thành số trần
        (2.0, 2_000_000_000),
        (800, 800_000_000),
        (3_100_000_000, 3_100_000_000),  # đã là đồng thì giữ nguyên
    ],
)
def test_o_excel_la_so_tran_thi_doan_don_vi(raw, expected):
    """Excel đổi vài ô giá thành số, mất chữ 'tỷ'. Không đoán thì 3,55 tỷ → 3 đồng."""
    assert parse_price_vnd(raw) == expected


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        (3_100_000_000, "3,1 tỷ"),
        (2_000_000_000, "2 tỷ"),
        (800_000_000, "800 triệu"),
        (None, ""),
    ],
)
def test_format_lai_thanh_nhan_hien_thi(price, expected):
    assert format_price_label(price) == expected


def test_parse_roi_format_lai_ra_dung_ban_goc():
    for raw in ("3,1 tỷ", "1,8 tỷ", "2 tỷ"):
        assert format_price_label(parse_price_vnd(raw)) == raw


# ---------------------------------------------------------------- Diện tích


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("49m2", 49.0),
        ("28m2", 28.0),
        ("33,5m2", 33.5),
        ("27.2m2", 27.2),
        ("34.7m2", 34.7),
        ("45 m²", 45.0),
    ],
)
def test_parse_dien_tich(raw, expected):
    assert parse_area_m2(raw) == pytest.approx(expected)


def test_dien_tich_dung_lan_dau_phay_va_dau_cham():
    """File gốc có cả '33,5m2' lẫn '27.2m2' — cả hai đều là thập phân."""
    assert parse_area_m2("33,5m2") == 33.5
    assert parse_area_m2("27.2m2") == 27.2


# ---------------------------------------------------------------- Loại căn


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 PN, 1WC", (1, 1)),
        ("1PN, 1WC", (1, 1)),
        ("2 PN, 2WC", (2, 2)),
        ("2PN, 1WC", (2, 1)),
        ("3 PN, 2WC", (3, 2)),
        ("Studio", (0, 1)),
    ],
)
def test_parse_loai_can(raw, expected):
    assert parse_layout(raw) == expected


def test_co_hay_khong_co_dau_cach_deu_ra_cung_mot_loai():
    """'1 PN, 1WC' và '1PN, 1WC' là cùng một loại — file gốc đếm thành hai."""
    assert normalize_layout_label("1 PN, 1WC") == normalize_layout_label("1PN, 1WC")


def test_studio_la_khong_phong_ngu():
    assert normalize_layout_label("Studio") == "Studio"
    assert parse_layout("Studio")[0] == 0


# ---------------------------------------------------------------- Hướng


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Đông Nam", ["Đông Nam"]),
        ("Đông Bắc", ["Đông Bắc"]),
        ("Tây Nam", ["Tây Nam"]),
        ("Đông Bắc - Đông Nam", ["Đông Bắc", "Đông Nam"]),
        ("Đông Nam - Tây Nam", ["Đông Nam", "Tây Nam"]),
        ("", []),
        (None, []),
    ],
)
def test_parse_huong(raw, expected):
    assert parse_directions(raw) == expected


def test_can_hai_huong_tra_ve_ca_hai():
    """Tool phong thuỷ phải khớp được cả hai hướng của căn góc."""
    assert len(parse_directions("Đông Bắc - Đông Nam")) == 2


# ---------------------------------------------------------------- Linh tinh


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(27.0, 27), ("27", 27), (2702.0, 2702), (None, None), ("", None), ("abc", None)],
)
def test_parse_so_nguyen(raw, expected):
    assert parse_int(raw) == expected


def test_clean_text_bo_xuong_dong_trong_o_excel():
    assert clean_text("Mã Căn \n(VOP)") == "Mã Căn (VOP)"
    assert clean_text("  nhiều   khoảng   trắng  ") == "nhiều khoảng trắng"
    assert clean_text(None) == ""
