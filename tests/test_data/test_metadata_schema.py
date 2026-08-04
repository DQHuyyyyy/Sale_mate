"""Test cấu trúc dữ liệu chung (metadata schema) — mục 2 Data Handling.

Đảm bảo CẢ 3 nguồn (tồn kho, batdongsan, meeyland) sinh ra metadata đủ khoá
bắt buộc — không phải chỉ đọc code mà tin, mà chạy qua từng nguồn thật.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from src.data.crawling.batdongsan import parse_listing_detail as parse_batdongsan
from src.data.crawling.meeyland import parse_listing_detail as parse_meeyland
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.metadata_schema import REQUIRED_METADATA_KEYS, validate_metadata
from src.data.sources.inventory import InventoryUnit, unit_to_document

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_BATDONGSAN_HTML = """
<html><head>
<link rel="canonical" href="https://batdongsan.com.vn/ban-can-ho-vinhomes-ocean-park/can-2pn-pr123456" />
</head><body>
<h1 class="re__pr-title">Bán căn hộ 2PN Vinhomes Ocean Park</h1>
<div class="re__detail-content js__pr-description">Căn góc view hồ.</div>
</body></html>
"""

_MEEYLAND_HTML = """
<html><head>
<meta property="og:title" content="Vinhomes Ocean Park - căn góc 2PN">
<meta name="description" content="Diện tích 64m², giá 4.200.000.000 VNĐ. Mã tin rao: 306086850.">
</head><body>
<div class="article-description"><div class="break-words"><p>Căn góc thoáng sáng.</p></div></div>
</body></html>
"""


def test_validate_metadata_bao_thieu_khoa():
    with pytest.raises(ValueError, match="visibility"):
        validate_metadata({key: None for key in REQUIRED_METADATA_KEYS - {"visibility"}}, doc_id="test:1")


def test_validate_metadata_du_khoa_thi_khong_raise():
    validate_metadata({key: None for key in REQUIRED_METADATA_KEYS}, doc_id="test:1")


def test_document_tu_batdongsan_dat_schema():
    doc = parse_batdongsan(_BATDONGSAN_HTML, "https://batdongsan.com.vn/test-pr123456")
    assert doc is not None
    validate_metadata(doc.metadata, doc_id=doc.doc_id)


def test_document_tu_meeyland_dat_schema():
    doc = parse_meeyland(_MEEYLAND_HTML, "https://meeyland.com/test/306086850")
    assert doc is not None
    validate_metadata(doc.metadata, doc_id=doc.doc_id)


def test_document_tu_inventory_dat_schema():
    unit = InventoryUnit(
        unit_code="VOP398",
        building="R103",
        floor="27",
        room_no="2702",
        unit_type="1 PN, 1WC",
        area_m2="49m2",
        direction="Đông Nam",
        view="View biển hồ",
        legal_status="Sẵn sổ",
        price_label="3,1 tỷ",
        furniture="Full nội thất",
        status="available",
        photos=["IMG_1.jpg"],
    )
    doc = unit_to_document(unit)
    validate_metadata(doc.metadata, doc_id=doc.doc_id)


def test_chunk_version_lay_dung_tu_ngay_ingest():
    """Chunk.version đã định nghĩa sẵn trong contracts.py nhưng trước đây luôn
    rỗng vì không nguồn nào set metadata['version'] — giờ phải có giá trị thật.
    """
    doc = parse_batdongsan(_BATDONGSAN_HTML, "https://batdongsan.com.vn/test-pr123456")
    assert doc is not None

    chunks = ParagraphChunker().split(doc)
    assert chunks
    for chunk in chunks:
        assert _ISO_DATE_RE.match(chunk.version), f"version không đúng dạng ISO date: {chunk.version!r}"
        assert chunk.version == datetime.now(UTC).date().isoformat()
