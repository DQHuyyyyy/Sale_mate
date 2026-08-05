"""Test parser crawler meeyland.com — dùng HTML giả, không gọi mạng."""

from __future__ import annotations

from src.data.crawling.meeyland import _extract_listing_paths, parse_listing_detail

_DETAIL_HTML = """
<html><head>
<meta property="og:title" content="Vinhomes Ocean Park - căn góc 2PN siêu đẹp giá tốt - hiếm! Giá 4.2 tỷ">
<meta name="description" content="Meeyland có 11 ảnh về căn hộ chung cư Vinhomes Ocean Park, H. Gia Lâm, Tp. Hà Nội. Diện tích 64m², giá 4.200.000.000  VNĐ. Mã tin rao: 306086850. Môi giới đăng tin.">
</head><body>
<div class="article-description"><div class="break-words"><p>Căn góc thoáng sáng, sổ đỏ cầm tay, nội thất đầy đủ.</p></div></div>
<img src="https://io.meeymedia.com/meeyland-ai/images/2025/12/anh1_wm.jpg"/>
<img data-src="https://io.meeymedia.com/meeyland-ai/images/2025/12/anh2_wm.jpg"/>
</body></html>
"""

_SEARCH_HTML = """
<html><body>
<a href="/ban-can-ho-chung-cu-gia-lam-ha-noi-i1422/307485275">Tin 1</a>
<a href="/ban-can-ho-chung-cu-gia-lam-ha-noi-i1422/305688394?utm=abc">Tin 2</a>
<a href="/ban-can-ho-chung-cu-gia-lam-ha-noi-i1422/307485275">Tin 1 (lặp lại)</a>
<a href="/tin-tuc/bai-viet-khac">Bài viết không phải tin đăng</a>
</body></html>
"""


def test_parse_dung_du_truong():
    doc = parse_listing_detail(_DETAIL_HTML, "https://meeyland.com/test/306086850")

    assert doc is not None
    assert doc.doc_id == "meeyland:306086850"
    assert "Diện tích 64m²" in doc.text
    assert "Căn góc thoáng sáng" in doc.text
    assert doc.metadata["image_urls"] == [
        "https://io.meeymedia.com/meeyland-ai/images/2025/12/anh1_wm.jpg",
        "https://io.meeymedia.com/meeyland-ai/images/2025/12/anh2_wm.jpg",
    ]


def test_trang_khong_co_og_title_thi_tra_none():
    assert parse_listing_detail("<html><body>Trang lỗi</body></html>", "https://meeyland.com/x") is None


def test_loai_bo_so_dien_thoai_moi_gioi_khoi_tieu_de_va_mo_ta():
    html = """
<html><head>
<meta property="og:title" content="Bán căn 2PN full nội thất, giá 3,25 tỷ. LH ngay 0946622828">
<meta name="description" content="Diện tích 64m², giá 4.200.000.000  VNĐ. Mã tin rao: 306086850.">
</head><body>
<div class="article-description"><p>Xem nhà thực tế liên hệ Zalo: 0908823226 nhé.</p></div>
</body></html>
"""
    doc = parse_listing_detail(html, "https://meeyland.com/test/306086850")

    assert doc is not None
    assert "0946622828" not in doc.title
    assert "0946622828" not in doc.text
    assert "0908823226" not in doc.text
    # Giá tiền có dấu chấm ngăn nhóm số không được coi là SĐT, phải giữ nguyên.
    assert "4.200.000.000" in doc.text


def test_extract_listing_paths_loc_dung_va_bo_trung():
    paths = _extract_listing_paths(_SEARCH_HTML)

    assert paths == [
        "/ban-can-ho-chung-cu-gia-lam-ha-noi-i1422/307485275",
        "/ban-can-ho-chung-cu-gia-lam-ha-noi-i1422/305688394",
    ]
