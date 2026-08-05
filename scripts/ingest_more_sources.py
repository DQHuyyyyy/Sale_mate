"""Nạp tin đăng Vinhomes Ocean Park từ meeyland.com vào Qdrant.

Site này không bị chặn bot (khác batdongsan.com.vn) nên crawl trực tiếp
được, không cần thu thập thủ công.

Chạy (cần `make infra` bật Qdrant trước):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_more_sources.py
"""

from __future__ import annotations

import asyncio

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.crawling import meeyland
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.pipelines import IngestPipeline
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    documents = await meeyland.crawl_vinhomes_ocean_park(meeyland.CrawlLimits(max_search_pages=20, max_listings=None))
    logger.info("Tổng %d tài liệu từ meeyland", len(documents))

    if settings.has_openai_key:
        embedder = OpenAIEmbedder(
            settings.openai_api_key, model=settings.embedding_model, dimension=settings.embedding_dim
        )
    else:
        logger.warning("Chưa có OPENAI_API_KEY hợp lệ — dùng FakeEmbedder")
        embedder = FakeEmbedder(dimension=64)

    store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, api_key=settings.qdrant_api_key)
    pipeline = IngestPipeline(ParagraphChunker(), embedder, store)

    total_chunks = 0
    for document in documents:
        report = await pipeline.ingest_document(document)
        total_chunks += report.chunks

    logger.info("Đã ingest %d tài liệu, tổng %d chunk", len(documents), total_chunks)

    # Mục 6 Data Handling: tin đã bị gỡ khỏi site (không còn trong lần crawl
    # này) được đánh dấu is_active=False thay vì để mãi "active" sai sự thật.
    # Giữ nguyên text cũ (không xoá) — coi như lịch sử phiên bản đã hết hiệu lực.
    current_doc_ids = {document.doc_id for document in documents}
    existing_doc_ids = await store.list_active_doc_ids("meeyland.com")
    stale_doc_ids = existing_doc_ids - current_doc_ids
    if stale_doc_ids:
        await store.mark_inactive(list(stale_doc_ids))
        logger.info("Đánh dấu %d tin meeyland.com đã gỡ khỏi site thành is_active=False", len(stale_doc_ids))

    count = await store.count()
    logger.info("Qdrant collection '%s' hiện có %d chunk", settings.qdrant_collection, count)


if __name__ == "__main__":
    asyncio.run(main())
