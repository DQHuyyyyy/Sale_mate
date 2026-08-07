"""Nạp mô tả tồn kho căn hộ (CSV) vào Qdrant thật.

CSV (data/raw/inventory.csv) chính là "nguồn thô" — không cần bước lưu text
thô riêng như crawl web. Đúng luồng còn lại: CSV -> Markdown (có heading) ->
Chunking -> JSON chứa chunk (eval/results/inventory_chunks.json) -> Embedding
-> Qdrant.

Chạy (cần `make infra` bật Qdrant trước, và OPENAI_API_KEY hợp lệ trong .env):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_inventory.py

Không có OPENAI_API_KEY thì tự rơi về FakeEmbedder — vẫn ingest được vào
Qdrant, chỉ là chất lượng truy hồi thấp hơn (không hiểu ngữ nghĩa thật).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.ingestion.chunk_export import chunk_and_export_json
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.sources.inventory import load_inventory_csv, units_to_documents
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

CHUNKS_JSON_PATH = Path(__file__).resolve().parents[1] / "eval" / "results" / "inventory_chunks.json"


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    units = load_inventory_csv()
    logger.info("Nạp được %d căn từ CSV", len(units))

    # ---- Bước Parsing -> Markdown (xem src/data/sources/inventory.py) ----
    documents = units_to_documents(units)

    # ---- Bước Chunking + xuất JSON: Markdown -> chunk -> file JSON tường minh ----
    all_chunks = chunk_and_export_json(documents, ParagraphChunker(), CHUNKS_JSON_PATH)
    logger.info("Đã chunk %d tài liệu -> %d chunk, ghi ra %s", len(documents), len(all_chunks), CHUNKS_JSON_PATH)

    # ---- Bước Embedding ----
    if settings.has_openai_key:
        embedder = OpenAIEmbedder(
            settings.openai_api_key, model=settings.embedding_model, dimension=settings.embedding_dim
        )
    else:
        logger.warning("Chưa có OPENAI_API_KEY hợp lệ — dùng FakeEmbedder")
        embedder = FakeEmbedder(dimension=64)

    vectors = await embedder.embed_texts([c.text for c in all_chunks])

    # ---- Bước đẩy lên Vector DB (Qdrant) ----
    store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, api_key=settings.qdrant_api_key)
    await store.ensure_collection(embedder.dimension)
    for document in documents:
        await store.delete_by_doc(document.doc_id)  # nạp lại thì thay bản cũ, không cộng dồn
    await store.upsert(all_chunks, vectors)

    logger.info("Đã ingest %d tài liệu, tổng %d chunk", len(documents), len(all_chunks))

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
