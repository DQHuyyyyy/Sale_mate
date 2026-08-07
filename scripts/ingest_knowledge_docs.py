"""Nạp tài liệu kiến thức chung (chính sách, thủ tục, tiện ích...) vào Qdrant.

Đọc toàn bộ file .md trong data/raw/knowledge/ (mỗi file có front-matter
title/section/visibility) — khác CSV tồn kho và HTML crawl tin đăng.

Đúng luồng: Markdown -> Chunking -> JSON chứa chunk -> Embedding ->
vector + nội dung + metadata -> Qdrant. Bước "JSON chứa chunk" ghi ra
eval/results/knowledge_chunks.json TRƯỚC khi embed — để soi được đúng nội
dung/metadata từng chunk sẽ lên Qdrant, không phải suy đoán qua log.

Chạy (cần `make infra` hoặc Qdrant Cloud đã cấu hình trong .env):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_knowledge_docs.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.ingestion.chunk_export import chunk_and_export_json
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.metadata_schema import validate_metadata
from src.data.sources.knowledge_docs import load_knowledge_dir
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

CHUNKS_JSON_PATH = Path(__file__).resolve().parents[1] / "eval" / "results" / "knowledge_chunks.json"


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

    count = await store.count()
    logger.info("Qdrant collection '%s' hiện có %d chunk", settings.qdrant_collection, count)


if __name__ == "__main__":
    asyncio.run(main())
