"""Module DATA — đường GHI dữ liệu.

    crawl → parse → chunk → embed → vector store

Chủ sở hữu: viet

Cấu trúc:
    contracts.py        Chunk · Embedder · VectorStore · RetrievalFilter (đóng băng)
    crawling/           meeyland · batdongsan
    sources/            inventory (CSV) · knowledge_docs (.md)
    ingestion/          chunkers · embedders · parsers · metadata_schema
    stores/             memory_store (dev/test) · qdrant_store (prod) · inventory_db
    pipeline.py         IngestPipeline — chunk → embed → ghi
    ingest.py           build_pipeline() + 4 nguồn
    cli.py              python -m src.cli

Phần ĐỌC (truy hồi, rerank, grounding) ở `src/rag/`. Phụ thuộc đi một chiều:
rag → data. Data không bao giờ import rag.

Module khác chỉ import từ `src.data.contracts`, không import class cụ thể trong
stores/ hay ingestion/.
"""

from src.data.contracts import (
    Chunk,
    Chunker,
    DocumentLoader,
    Embedder,
    LoadedDocument,
    RetrievalFilter,
    VectorStore,
)

__all__ = [
    "Chunk",
    "Chunker",
    "DocumentLoader",
    "Embedder",
    "LoadedDocument",
    "RetrievalFilter",
    "VectorStore",
]
