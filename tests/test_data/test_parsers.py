"""Test chuẩn hoá dữ liệu thô.

Mọi giá trị đầu vào ở đây đều lấy từ file crawl thật (Data_crawl/Data .xlsx),
không phải ví dụ bịa ra.
"""

from __future__ import annotations

import pytest

from src.data.ingestion.parsers import (
    clean_text,
    detect_property_type,
    extract_building_code,
    format_price_label,
    normalize_layout_label,
    parse_area_m2,
    parse_directions,
    parse_int,
    parse_layout,
    parse_price_vnd,
    sanitize_text,
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


# ---------------------------------------------------------------- Loại hình BĐS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bán căn hộ 2PN Vinhomes Ocean Park", "Chung cư"),
        ("Bán CC studio tại Vinhomes Ocean Park Gia Lâm", "Chung cư"),
        ("33 tỷ! Sở hữu biệt thự song lập Sao Biển gần hồ điều hoà", "Biệt thự"),
        ("Cho thuê mặt bằng, môi giới liên hệ ngay", None),
        ("", None),
        (None, None),
    ],
)
def test_detect_property_type(raw, expected):
    assert detect_property_type(raw) == expected


def test_detect_property_type_biet_thu_lien_ke_uu_tien_truoc_chung_cu():
    """'biệt thự liền kề' không được nhận nhầm thành 'chung cư' dù câu dài có
    thể chứa từ khoá chung — cụm cụ thể phải thắng."""
    assert detect_property_type("Bán nhà biệt thự liền kề khu Sao Biển, gần chung cư The Sapphire") == "Biệt thự"


def test_detect_property_type_bo_qua_khi_la_view_khong_phai_loai_hinh_cua_can():
    """Bug thật meeyland:307500673 — căn 1PN nhưng tiêu đề nhắc 'view... biệt
    thự' (tả cảnh quan nhìn thấy, không phải bản thân căn là biệt thự)."""
    assert detect_property_type("Bán căn 1PN full đồ siêu đẹp, view hồ và biệt thự siêu thoáng. LH: ***") is None


def test_detect_property_type_view_khong_chan_khop_that_o_cho_khac():
    """Chỉ bỏ qua đúng khớp bị 'view' đứng trước — khớp thật ở chỗ khác trong
    câu vẫn phải nhận ra."""
    assert detect_property_type("Bán biệt thự song lập, view hồ tuyệt đẹp") == "Biệt thự"


# ---------------------------------------------------------------- Mã toà


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Vị trí: Tòa S1.12 xuống sảnh vài bước chân ra hồ Ngọc Trai", "S1.12"),
        ("Căn hộ tại toà R105, view đẹp", "R105"),
        ("Nằm ở The Sapphire 2 - Vinhomes Ocean Park", None),  # tên khu, không phải mã toà cụ thể
        ("Mã tin rao: 307514797", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_building_code(raw, expected):
    assert extract_building_code(raw) == expected


# ---------------------------------------------------------------- Làm sạch văn bản dài


@pytest.mark.parametrize(
    "price_text",
    [
        "giá 10.000.000.000 VNĐ",  # 10 tỷ tròn — bug thật: từng bị ăn còn "10."
        "giá 33.000.000.000 VNĐ",
        "giá 51.400.000.000 VNĐ",
        "giá 100.000.000.000 VNĐ",
        "giá 800.000.000 VNĐ",
        "giá 1.000.000.000 VNĐ",
        "giá 4.200.000.000 VNĐ",
    ],
)
def test_sanitize_text_khong_duoc_an_gia_tien_dinh_dang_tron_so(price_text):
    """Bug thật 12/08/2026: regex SĐT khớp nhầm vào GIỮA dãy số giá tiền
    tròn (nhiều số 0 liên tiếp), biến '10.000.000.000' thành '1' — sai số,
    đúng thứ nguyên tắc 'không bịa số' của dự án cấm."""
    assert sanitize_text(price_text) == price_text


@pytest.mark.parametrize(
    "raw",
    [
        "LH: 0912345678",
        "LH em 0912 345 678 nhé",
        "LH em 0912-345-678 nhé",
        "Zalo: 0987 654 321",
    ],
)
def test_sanitize_text_van_xoa_dung_sdt_that(raw):
    """Số điện thoại thật (không dùng dấu chấm ngăn nhóm) vẫn phải bị xoá —
    sửa bug ăn nhầm giá tiền không được làm mất khả năng lọc SĐT."""
    result = sanitize_text(raw)
    assert "0912" not in result
    assert "0987" not in result


def test_sanitize_text_giu_nguyen_cau_truc_markdown():
    """Bug thật 12/08/2026: một cách làm sạch khác (re.sub gộp cả xuống dòng)
    phá sạch heading/bảng/danh sách. sanitize_text() PHẢI giữ nguyên cấu trúc
    đoạn — ParagraphChunker dựa vào dòng trống để tách chunk."""
    raw = (
        "# Bảng giá dạng văn bản\n\n"
        "## Đơn giá theo từng khu\n\n"
        "| Mục | Giá trị |\n"
        "|---|---|\n"
        "| Đơn giá niêm yết | 13.000 đồng/m²/tháng |\n\n"
        "- Gạch đầu dòng 1\n"
        "- Gạch đầu dòng 2"
    )
    result = sanitize_text(raw)

    assert "# Bảng giá dạng văn bản" in result
    assert "## Đơn giá theo từng khu" in result
    assert "13.000 đồng/m²/tháng" in result
    assert "- Gạch đầu dòng 1" in result
    assert "- Gạch đầu dòng 2" in result
    # Ranh giới đoạn (dòng trống) phải còn — đây chính là thứ ParagraphChunker
    # dùng để tách chunk, mất cái này là mất luôn khả năng chunk theo cấu trúc.
    assert "\n\n" in result
    # Mỗi dòng gốc vẫn phải tách dòng riêng, không bị dồn thành 1 dòng.
    assert result.count("\n") >= 6


def test_sanitize_text_xoa_sdt_va_cum_spam():
    # SĐT KHÔNG dùng dấu chấm ngăn nhóm (đúng thực tế đã quan sát trên
    # meeyland/batdongsan) — cố ý, xem ghi chú tại _PHONE_PATTERN: dấu chấm
    # để dành riêng cho giá tiền, dùng chung sẽ ăn nhầm số 0 tròn trong giá.
    result = sanitize_text("Chính chủ cần bán gấp căn đẹp. LH: 0912 345 678. Siêu phẩm, rẻ nhất thị trường!!!")

    assert "0912" not in result
    assert "chính chủ" not in result.lower()
    assert "siêu phẩm" not in result.lower()
    assert "rẻ nhất thị trường" not in result.lower()
    # Không để lại vệt dấu câu rời rạc kiểu "đẹp. . , !"
    assert ". ." not in result
    assert " , " not in result


def test_sanitize_text_xoa_html_tag_entity_va_url():
    result = sanitize_text("<p>Xem thêm tại https://example.com &nbsp; căn đẹp</p>")

    assert "<p>" not in result
    assert "</p>" not in result
    assert "https://" not in result
    assert "&nbsp;" not in result
    assert "căn đẹp" in result


def test_sanitize_text_xoa_ky_tu_unicode_an():
    result = sanitize_text("Căn\xa0đẹp​view hồ")

    assert "\xa0" not in result
    assert "​" not in result


@pytest.mark.parametrize("raw", [None, "", "nan", "None", "NULL", "n/a"])
def test_sanitize_text_placeholder_rac_tra_rong(raw):
    assert sanitize_text(raw) == ""


def test_sanitize_text_khac_clean_text_o_cho_giu_xuong_dong():
    """clean_text() dùng cho ô Excel một dòng — gộp cả xuống dòng, ĐÚNG cho
    mục đích đó. sanitize_text() dùng cho văn bản dài — không được gộp."""
    raw = "Dòng 1\n\nDòng 2"

    assert clean_text(raw) == "Dòng 1 Dòng 2"
    assert sanitize_text(raw) == "Dòng 1\n\nDòng 2"
