"""Test truy hồi: store, phân quyền, chunker, retriever."""

from __future__ import annotations

import pytest

from src.data.contracts import Chunk, LoadedDocument, RetrievalFilter
from src.data.crawling.meeyland import parse_listing_detail
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.pipelines import IngestPipeline
from src.data.retrieval.rerankers import KeywordOverlapReranker, PassthroughReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.sources.inventory import InventoryUnit, unit_to_document


def _chunk(chunk_id: str, text: str, **kwargs) -> Chunk:
    return Chunk(id=chunk_id, text=text, doc_id=kwargs.pop("doc_id", "d1"), **kwargs)


# ---------------- Store + phân quyền ----------------


@pytest.mark.asyncio
async def test_upsert_va_dem(memory_store, fake_embedder):
    chunks = [_chunk("c1", "căn hộ hai phòng ngủ"), _chunk("c2", "nhà phố năm tầng")]
    vectors = await fake_embedder.embed_texts([c.text for c in chunks])

    await memory_store.upsert(chunks, vectors)

    assert await memory_store.count() == 2


@pytest.mark.asyncio
async def test_tai_lieu_noi_bo_khong_lot_ra_khi_chi_co_quyen_public(memory_store, fake_embedder):
    """Phân quyền phải chặn NGAY tại truy vấn, không lọc ở tầng sau."""
    chunks = [
        _chunk("pub", "chính sách công khai", visibility="public"),
        _chunk("int", "chính sách nội bộ", visibility="internal"),
    ]
    vectors = await fake_embedder.embed_texts([c.text for c in chunks])
    await memory_store.upsert(chunks, vectors)

    query = await fake_embedder.embed_query("chính sách")
    found = await memory_store.search(query, filters=RetrievalFilter(visibility=["public"]), limit=10)

    assert [c.id for c in found] == ["pub"]


@pytest.mark.asyncio
async def test_ton_kho_that_khong_lot_ra_portal_cong_khai_tin_dang_thi_co(memory_store, fake_embedder):
    """Mục 6 Data Handling — phân quyền dữ liệu, kiểm tra bằng đúng nguồn thật
    (không phải Chunk dựng tay): tồn kho nội bộ (visibility=internal) không
    được lọt ra khi portal công khai tìm kiếm (filter mặc định chỉ public),
    trong khi tin đăng bên thứ 3 (visibility=public) vẫn thấy bình thường.
    """
    inventory_doc = unit_to_document(
        InventoryUnit(
            unit_code="VOP999",
            building="R199",
            floor="9",
            room_no="0909",
            unit_type="2PN",
            area_m2="60m2",
            direction="Đông Nam",
            view="View hồ trung tâm độc quyền",
            legal_status="Sẵn sổ",
            price_label="4 tỷ",
            furniture="Full nội thất",
            status="available",
        )
    )
    listing_html = """
<html><head>
<meta property="og:title" content="Bán căn view hồ trung tâm độc quyền Vinhomes Ocean Park">
<meta name="description" content="Diện tích 60m², giá 4.000.000.000 VNĐ.">
</head><body><div class="article-description"><p>Căn đẹp, view hồ trung tâm độc quyền.</p></div></body></html>
"""
    listing_doc = parse_listing_detail(listing_html, "https://meeyland.com/test/999999")
    assert listing_doc is not None

    pipeline = IngestPipeline(ParagraphChunker(), fake_embedder, memory_store)
    await pipeline.ingest_document(inventory_doc)
    await pipeline.ingest_document(listing_doc)

    retriever = DefaultRetriever(fake_embedder, memory_store, PassthroughReranker())

    # Portal công khai: filter mặc định (chỉ public) — KHÔNG được thấy tồn kho.
    public_result = await retriever.retrieve("view hồ trung tâm độc quyền", filters=RetrievalFilter())
    public_doc_ids = {chunk.doc_id for chunk in public_result.chunks}
    assert inventory_doc.doc_id not in public_doc_ids
    assert listing_doc.doc_id in public_doc_ids

    # Admin/Sale: filter gồm cả internal — PHẢI thấy tồn kho.
    internal_result = await retriever.retrieve(
        "view hồ trung tâm độc quyền", filters=RetrievalFilter(visibility=["public", "internal"])
    )
    internal_doc_ids = {chunk.doc_id for chunk in internal_result.chunks}
    assert inventory_doc.doc_id in internal_doc_ids


@pytest.mark.asyncio
async def test_ban_het_hieu_luc_bi_loai(memory_store, fake_embedder):
    chunks = [
        _chunk("new", "bảng giá tháng bảy", is_active=True),
        _chunk("old", "bảng giá tháng sáu", is_active=False),
    ]
    vectors = await fake_embedder.embed_texts([c.text for c in chunks])
    await memory_store.upsert(chunks, vectors)

    query = await fake_embedder.embed_query("bảng giá")
    found = await memory_store.search(query, filters=RetrievalFilter(), limit=10)

    assert [c.id for c in found] == ["new"]


@pytest.mark.asyncio
async def test_xoa_theo_doc_id(memory_store, fake_embedder):
    chunks = [_chunk("a", "một", doc_id="d1"), _chunk("b", "hai", doc_id="d2")]
    vectors = await fake_embedder.embed_texts([c.text for c in chunks])
    await memory_store.upsert(chunks, vectors)

    removed = await memory_store.delete_by_doc("d1")

    assert removed == 1
    assert await memory_store.count() == 1


@pytest.mark.asyncio
async def test_loc_cau_truc_bat_dong_san(memory_store, fake_embedder):
    """Test bộ lọc cấu trúc (giá, diện tích, số phòng, tòa, loại căn) tách biệt khỏi ngữ nghĩa."""
    c1 = _chunk("c1", "Căn 2PN sang trọng", metadata={"price": 3.5, "area": 65.0, "num_bedrooms": 2, "building": "S1.01", "property_type": "2PN"})
    c2 = _chunk("c2", "Căn 3PN rộng rãi", metadata={"price": 5.0, "area": 90.0, "num_bedrooms": 3, "building": "S1.02", "property_type": "3PN"})
    c3 = _chunk("c3", "Căn Studio tiện nghi", metadata={"price": 2.0, "area": 35.0, "num_bedrooms": 1, "building": "S1.01", "property_type": "Studio"})

    chunks = [c1, c2, c3]
    vectors = await fake_embedder.embed_texts([c.text for c in chunks])
    await memory_store.upsert(chunks, vectors)

    query_vec = await fake_embedder.embed_query("căn hộ")

    # Lọc khoảng giá [3.0, 4.0] tỷ
    found = await memory_store.search(query_vec, filters=RetrievalFilter(min_price=3.0, max_price=4.0), limit=10)
    assert [c.id for c in found] == ["c1"]

    # Lọc diện tích >= 80m²
    found = await memory_store.search(query_vec, filters=RetrievalFilter(min_area=80.0), limit=10)
    assert [c.id for c in found] == ["c2"]

    # Lọc theo số phòng = 2
    found = await memory_store.search(query_vec, filters=RetrievalFilter(num_bedrooms=2), limit=10)
    assert [c.id for c in found] == ["c1"]

    # Lọc kết hợp Tòa S1.01 & Loại căn Studio
    found = await memory_store.search(query_vec, filters=RetrievalFilter(building="S1.01", property_type="Studio"), limit=10)
    assert [c.id for c in found] == ["c3"]


def test_qdrant_filter_translation():
    """Kiểm tra việc chuyển đổi RetrievalFilter thành Qdrant Filter object."""
    from qdrant_client import models
    from src.data.stores.qdrant_store import _to_qdrant_filter

    f = RetrievalFilter(
        min_price=3.0,
        max_price=5.0,
        min_area=50.0,
        num_bedrooms=2,
        building="S1.01",
        property_type="2PN",
    )
    qdrant_filter = _to_qdrant_filter(f)

    assert isinstance(qdrant_filter, models.Filter)
    assert isinstance(qdrant_filter.must, list)
    assert len(qdrant_filter.must) >= 6

    # Verify presence of range and match conditions
    keys_contained = [cond.key for cond in qdrant_filter.must if isinstance(cond, models.FieldCondition)]
    assert "price" in keys_contained
    assert "area" in keys_contained
    assert "num_bedrooms" in keys_contained
    assert "building" in keys_contained
    assert "property_type" in keys_contained


# ---------------- Chunker ----------------


def test_chunker_ton_trong_ranh_gioi_doan():
    document = LoadedDocument(
        doc_id="d1",
        title="Chính sách",
        text="Đoạn một.\n\nĐoạn hai dài hơn một chút.\n\nĐoạn ba.",
    )

    chunks = ParagraphChunker(target_chars=1000).split(document)

    assert len(chunks) == 1
    assert chunks[0].doc_title == "Chính sách"


def test_chunker_cat_khi_vuot_kich_thuoc():
    document = LoadedDocument(doc_id="d1", title="T", text="\n\n".join(["x" * 400] * 5))

    chunks = ParagraphChunker(target_chars=500, overlap_chars=50).split(document)

    assert len(chunks) > 1
    assert all(chunk.doc_id == "d1" for chunk in chunks)


def test_chunker_van_ban_rong_thi_khong_sinh_chunk():
    chunks = ParagraphChunker().split(LoadedDocument(doc_id="d1", title="T", text="   "))

    assert chunks == []


def test_chunker_doan_dai_dung_sau_doan_ngan_van_bi_cat_dung_target():
    """Bug thật gặp trên dữ liệu meeyland: đoạn đầu ngắn (title) chiếm buffer,
    đoạn sau dài hơn target nhiều lần từng bị ghép nguyên vào buffer cũ thay vì
    cắt cứng — sinh chunk tới 3293 ký tự dù target=900. Không được lặp lại.
    """
    text = "Tiêu đề ngắn.\n\n" + "Mô tả dài. " * 100  # đoạn 2 dài hơn 900 nhiều lần
    document = LoadedDocument(doc_id="d1", title="T", text=text)

    chunks = ParagraphChunker(target_chars=900, overlap_chars=120).split(document)

    assert all(len(chunk.text) <= 900 for chunk in chunks), [len(c.text) for c in chunks]


# ---------------- Reranker ----------------


@pytest.mark.asyncio
async def test_passthrough_chi_cat_top_n():
    chunks = [_chunk(str(i), f"văn bản {i}") for i in range(5)]

    result = await PassthroughReranker().rerank("hỏi gì đó", chunks, top_n=2)

    assert [c.id for c in result] == ["0", "1"]


@pytest.mark.asyncio
async def test_keyword_reranker_day_chunk_trung_tu_khoa_len_dau():
    chunks = [
        _chunk("xa", "nội dung không liên quan", score=0.5),
        _chunk("gan", "chính sách chiết khấu cho khách", score=0.4),
    ]

    result = await KeywordOverlapReranker().rerank("chính sách chiết khấu", chunks, top_n=2)

    assert result[0].id == "gan"


# ---------------- Retriever + pipeline ----------------


@pytest.mark.asyncio
async def test_retriever_tra_ve_chunk_va_do_phu(memory_store, fake_embedder):
    document = LoadedDocument(doc_id="d1", title="Chính sách", text="Chiết khấu cho khách hàng là năm phần trăm.")
    pipeline = IngestPipeline(ParagraphChunker(), fake_embedder, memory_store)
    report = await pipeline.ingest_document(document)
    assert report.ok

    retriever = DefaultRetriever(fake_embedder, memory_store, PassthroughReranker())
    result = await retriever.retrieve("chiết khấu cho khách hàng")

    assert result.chunks
    assert result.coverage > 0
    assert "Chiết khấu" in result.as_context()


@pytest.mark.asyncio
async def test_retriever_khong_co_du_lieu_thi_do_phu_bang_khong(memory_store, fake_embedder):
    retriever = DefaultRetriever(fake_embedder, memory_store, PassthroughReranker())

    result = await retriever.retrieve("câu hỏi bất kỳ")

    assert result.chunks == []
    assert result.is_sufficient(0.35) is False


@pytest.mark.asyncio
async def test_nap_lai_cung_doc_id_thi_thay_ban_cu(memory_store, fake_embedder):
    """Upload bản mới phải thay bản cũ — chỉ giữ bản đang hiệu lực."""
    pipeline = IngestPipeline(ParagraphChunker(), fake_embedder, memory_store)
    await pipeline.ingest_document(LoadedDocument(doc_id="d1", title="Bảng giá", text="Giá cũ."))

    report = await pipeline.ingest_document(LoadedDocument(doc_id="d1", title="Bảng giá", text="Giá mới."))

    assert report.replaced == 1
    assert await memory_store.count() == 1
