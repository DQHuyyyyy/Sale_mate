"""Nạp mô tả tồn kho căn hộ vào vector store qua IngestPipeline có sẵn.

Chạy:
    .venv/Scripts/python.exe scripts/ingest_inventory.py

Mặc định dùng FakeEmbedder + InMemoryVectorStore (không tốn tiền, không cần
Qdrant) — chỉ để chứng minh pipeline chạy đúng đầu-cuối. Muốn nạp vào Qdrant
thật: chạy `make infra` rồi đổi hai dòng khởi tạo bên dưới sang
OpenAIEmbedder/QdrantVectorStore (xem src/bootstrap.py để biết cách khởi tạo).
"""

from __future__ import annotations

import asyncio

from src.core.logging import get_logger, setup_logging
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder
from src.data.pipelines import IngestPipeline
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.sources.inventory import load_inventory_csv, units_to_documents
from src.data.stores.memory_store import InMemoryVectorStore

logger = get_logger(__name__)


async def main() -> None:
    setup_logging("INFO")

    units = load_inventory_csv()
    logger.info("Nạp được %d căn từ CSV", len(units))

    documents = units_to_documents(units)

    embedder = FakeEmbedder(dimension=64)
    store = InMemoryVectorStore()
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
