"""Nạp mô tả tồn kho căn hộ vào Qdrant thật qua IngestPipeline có sẵn.

Chạy (cần `make infra` bật Qdrant trước, và OPENAI_API_KEY hợp lệ trong .env):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_inventory.py

Không có OPENAI_API_KEY thì tự rơi về FakeEmbedder — vẫn ingest được vào
Qdrant, chỉ là chất lượng truy hồi thấp hơn (không hiểu ngữ nghĩa thật).
"""

from __future__ import annotations

import asyncio

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.pipelines import IngestPipeline
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.sources.inventory import load_inventory_csv, units_to_documents
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    units = load_inventory_csv()
    logger.info("Nạp được %d căn từ CSV", len(units))

    documents = units_to_documents(units)

    if settings.has_openai_key:
        embedder = OpenAIEmbedder(
            settings.openai_api_key, model=settings.embedding_model, dimension=settings.embedding_dim
        )
    else:
        logger.warning("Chưa có OPENAI_API_KEY hợp lệ — dùng FakeEmbedder")
        embedder = FakeEmbedder(dimension=64)

    store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection)
    pipeline = IngestPipeline(ParagraphChunker(), embedder, store)

    total_chunks = 0
    for document in documents:
        report = await pipeline.ingest_document(document)
        total_chunks += report.chunks

    logger.info("Đã ingest %d tài liệu, tổng %d chunk", len(documents), total_chunks)

    retriever = DefaultRetriever(embedder, store, KeywordOverlapReranker())
    demo_query = "căn có view hồ"
    result = await retriever.retrieve(demo_query)
    logger.info(
        "Demo truy hồi '%s' -> %d chunk, coverage=%.2f",
        demo_query,
        len(result.chunks),
        result.coverage,
    )
    for chunk in result.chunks:
        print(f"- {chunk.doc_id}: {chunk.text[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
