"""Nạp tin đăng batdongsan.com.vn (đã lưu thủ công) vào Qdrant.

Nguồn crawl tự động bị Cloudflare chặn (xem src/data/crawling/batdongsan.py),
nên dữ liệu đến từ các file .html người dùng tự lưu bằng trình duyệt
(Ctrl+S → "Chỉ HTML") đặt trong data/raw/.

Đúng luồng: HTML đã lưu -> text thô (data/raw/batdongsan_crawl_raw/) ->
Markdown -> Chunking -> JSON chứa chunk (eval/results/batdongsan_chunks.json)
-> Embedding -> Qdrant.

Chạy (cần `make infra` bật Qdrant trước):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/ingest_batdongsan.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.crawling.batdongsan import load_saved_detail_pages
from src.data.ingestion.chunk_export import chunk_and_export_json
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CHUNKS_JSON_PATH = Path(__file__).resolve().parents[1] / "eval" / "results" / "batdongsan_chunks.json"


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    # ---- Bước Parsing -> Markdown (xem src/data/crawling/batdongsan.py) ----
    documents = load_saved_detail_pages(RAW_DIR)
    logger.info("Đọc được %d tài liệu batdongsan.com.vn", len(documents))
    if not documents:
        logger.warning("Không đọc được tài liệu nào từ %s — dừng", RAW_DIR)
        return

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
    for demo_query in ("căn 3 phòng ngủ", "biệt thự song lập"):
        result = await retriever.retrieve(demo_query)
        logger.info("Demo truy hồi '%s' -> %d chunk, coverage=%.2f", demo_query, len(result.chunks), result.coverage)
        for chunk in result.chunks[:2]:
            print(f"- {chunk.doc_id}: {chunk.text[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
