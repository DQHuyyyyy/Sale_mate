"""Nạp tin đăng batdongsan.com.vn (đã lưu thủ công) vào vector store qua IngestPipeline.

Nguồn crawl tự động bị Cloudflare chặn (xem src/data/crawling/batdongsan.py),
nên dữ liệu đến từ các file .html người dùng tự lưu bằng trình duyệt
(Ctrl+S → "Chỉ HTML") đặt trong data/raw/.

Chạy:
    PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_batdongsan.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.logging import get_logger, setup_logging
from src.data.crawling.batdongsan import load_saved_detail_pages
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder
from src.data.pipelines import IngestPipeline
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.memory_store import InMemoryVectorStore

logger = get_logger(__name__)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


async def main() -> None:
    setup_logging("INFO")

    documents = load_saved_detail_pages(RAW_DIR)
    logger.info("Đọc được %d tài liệu batdongsan.com.vn", len(documents))

    embedder = FakeEmbedder(dimension=64)
    store = InMemoryVectorStore()
    pipeline = IngestPipeline(ParagraphChunker(), embedder, store)

    total_chunks = 0
    for document in documents:
        report = await pipeline.ingest_document(document)
        total_chunks += report.chunks

    logger.info("Đã ingest %d tài liệu, tổng %d chunk", len(documents), total_chunks)

    retriever = DefaultRetriever(embedder, store, KeywordOverlapReranker())
    for demo_query in ("căn 3 phòng ngủ", "biệt thự song lập"):
        result = await retriever.retrieve(demo_query)
        logger.info("Demo truy hồi '%s' -> %d chunk, coverage=%.2f", demo_query, len(result.chunks), result.coverage)
        for chunk in result.chunks[:2]:
            print(f"- {chunk.doc_id}: {chunk.text[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
