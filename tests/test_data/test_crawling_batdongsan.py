"""Test parser crawler batdongsan.com.vn — dùng HTML giả, không gọi mạng."""

from __future__ import annotations

from pathlib import Path

from src.data.crawling.batdongsan import _extract_listing_paths, load_saved_detail_pages, parse_listing_detail

_DETAIL_HTML = """
<html><head>
<link rel="canonical" href="https://batdongsan.com.vn/ban-can-ho-vinhomes-ocean-park/can-2pn-view-ho-pr123456" />
</head><body>
<h1 class="re__pr-title">Bán căn hộ 2PN Vinhomes Ocean Park</h1>
<div class="re__ldp-address">
    <span class="re__address-line-1">Vinhomes Ocean Park, Xã Dương Xá</span>
    <span class="re__address-line-2">(Gia Lâm, Hà Nội)</span>
</div>
<div class="re__pr-specs-content-item">
    <span class="re__pr-specs-content-item-title">Khoảng giá</span>
    <span class="re__pr-specs-content-item-value">3,45 tỷ</span>
</div>
<div class="re__pr-specs-content-item">
    <span class="re__pr-specs-content-item-title">Pháp lý</span>
    <span class="re__pr-specs-content-item-value">Sổ đỏ/ Sổ hồng</span>
</div>
<div class="re__detail-content js__pr-description">
    Căn góc view hồ, full nội thất.
    <span data-kyc-name="Môi giới">0987 654 ***</span>
</div>
<img class="pr-img" src="https://file4.batdongsan.com.vn/anh1.jpg" />
<img class="pr-img" data-src="https://file4.batdongsan.com.vn/anh2.jpg" />
<img class="pr-img" data-src="https://file4.batdongsan.com.vn/anh1.jpg" />
</body></html>
"""

_SEARCH_HTML = """
<html><body>
<a href="/ban-can-ho-vinhomes-ocean-park/can-2pn-view-ho-pr123456">Tin 1</a>
<a href="/ban-can-ho-vinhomes-ocean-park/can-3pn-full-noi-that-pr654321?utm=abc">Tin 2</a>
<a href="/ban-can-ho-vinhomes-ocean-park/can-2pn-view-ho-pr123456">Tin 1 (lặp lại)</a>
<a href="/tin-tuc/mot-bai-viet-khac">Bài viết không phải tin đăng</a>
</body></html>
"""


def test_parse_day_du_truong_thong_tin():
    doc = parse_listing_detail(_DETAIL_HTML, "https://batdongsan.com.vn/test-pr123")

    assert doc is not None
    assert doc.title == "Bán căn hộ 2PN Vinhomes Ocean Park"
    assert doc.doc_id == "batdongsan:123"
    assert doc.source_path == "https://batdongsan.com.vn/test-pr123"
    assert "3,45 tỷ" in doc.text
    assert "Sổ đỏ/ Sổ hồng" in doc.text
    assert "Căn góc view hồ" in doc.text


def test_loai_bo_so_dien_thoai_moi_gioi_khoi_mo_ta():
    doc = parse_listing_detail(_DETAIL_HTML, "https://batdongsan.com.vn/test-pr123")

    assert doc is not None
    assert "0987" not in doc.text


def test_lay_dung_url_anh_khong_trung_lap():
    doc = parse_listing_detail(_DETAIL_HTML, "https://batdongsan.com.vn/test-pr123")

    assert doc is not None
    assert doc.metadata["image_urls"] == [
        "https://file4.batdongsan.com.vn/anh1.jpg",
        "https://file4.batdongsan.com.vn/anh2.jpg",
    ]


def test_trang_khong_co_tieu_de_thi_tra_none():
    assert parse_listing_detail("<html><body>Trang lỗi</body></html>", "https://batdongsan.com.vn/x") is None


def test_extract_listing_paths_loc_dung_va_bo_trung():
    paths = _extract_listing_paths(_SEARCH_HTML)

    assert paths == [
        "/ban-can-ho-vinhomes-ocean-park/can-2pn-view-ho-pr123456",
        "/ban-can-ho-vinhomes-ocean-park/can-3pn-full-noi-that-pr654321",
    ]


def test_doc_file_html_da_luu_thu_cong_lay_dung_url_tu_canonical(tmp_path: Path):
    (tmp_path / "tin-1.html").write_text(_DETAIL_HTML, encoding="utf-8")

    docs = load_saved_detail_pages(tmp_path)

    assert len(docs) == 1
    assert docs[0].source_path == "https://batdongsan.com.vn/ban-can-ho-vinhomes-ocean-park/can-2pn-view-ho-pr123456"
    assert docs[0].doc_id == "batdongsan:123456"


def test_bo_qua_file_khong_co_canonical_url(tmp_path: Path):
    (tmp_path / "khong-co-url.html").write_text(
        "<html><body><h1 class='re__pr-title'>X</h1></body></html>", encoding="utf-8"
    )
    (tmp_path / "hop-le.html").write_text(_DETAIL_HTML, encoding="utf-8")

    docs = load_saved_detail_pages(tmp_path)

    assert len(docs) == 1
    assert docs[0].doc_id == "batdongsan:123456"
