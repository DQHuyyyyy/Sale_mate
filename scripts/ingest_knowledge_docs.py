"""Nạp tài liệu kiến thức chung (chính sách, thủ tục, tiện ích...) vào Qdrant.

Đọc toàn bộ file .md trong data/raw/knowledge/ (mỗi file có front-matter
title/section/visibility) — khác CSV tồn kho và HTML crawl tin đăng.

Chạy (cần `make infra` hoặc Qdrant Cloud đã cấu hình trong .env):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_knowledge_docs.py
"""

from __future__ import annotations

import asyncio

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.metadata_schema import validate_metadata
from src.data.pipelines import IngestPipeline
from src.data.sources.knowledge_docs import load_knowledge_dir
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    documents = load_knowledge_dir()
    logger.info("Đọc được %d tài liệu kiến thức chung", len(documents))
    if not documents:
        logger.warning("data/raw/knowledge/ rỗng hoặc chưa tồn tại — không có gì để ingest")
        return

    for document in documents:
        validate_metadata(document.metadata, doc_id=document.doc_id)

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
        logger.info("[%s] %s -> %d chunk", document.metadata["visibility"], document.title, report.chunks)

    logger.info("Đã ingest %d tài liệu, tổng %d chunk", len(documents), total_chunks)

    count = await store.count()
    logger.info("Qdrant collection '%s' hiện có %d chunk", settings.qdrant_collection, count)


if __name__ == "__main__":
    asyncio.run(main())
