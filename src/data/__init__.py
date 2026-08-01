"""Module DATA — xử lý dữ liệu phục vụ RAG.

Chủ sở hữu: dat

Cấu trúc:
    contracts.py          Protocol + DTO (đóng băng — sửa phải qua PR riêng)
    ingestion/            loaders · chunkers · embedders
    stores/               memory_store (dev/test) · qdrant_store (prod)
    retrieval/            retriever · rerankers
    pipelines.py          IngestPipeline

Module khác chỉ import từ src.data.contracts.
"""

from src.data.contracts import (
    Chunk,
    Chunker,
    DocumentLoader,
    Embedder,
    LoadedDocument,
    Reranker,
    RetrievalFilter,
    RetrievalResult,
    Retriever,
    VectorStore,
)

__all__ = [
    "Chunk",
    "Chunker",
    "DocumentLoader",
    "Embedder",
    "LoadedDocument",
    "Reranker",
    "RetrievalFilter",
    "RetrievalResult",
    "Retriever",
    "VectorStore",
]
