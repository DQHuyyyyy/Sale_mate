"""Retriever — mặt tiền cho toàn bộ khâu truy hồi.

Agent chỉ gọi Retriever.retrieve(); mọi chi tiết embed → search → rerank →
tính độ phủ nằm ở đây. Đổi store hay reranker không ảnh hưởng agent.
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.data.contracts import (
    Embedder,
    Reranker,
    RetrievalFilter,
    RetrievalResult,
    VectorStore,
)

logger = get_logger(__name__)


class DefaultRetriever:
    """Truy hồi ba bước: embed câu hỏi → search có lọc quyền → rerank."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        reranker: Reranker,
        *,
        top_k: int = 20,
        top_n: int = 5,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._top_k = top_k
        self._top_n = top_n

    async def retrieve(
        self,
        query: str,
        *,
        filters: RetrievalFilter | None = None,
        top_k: int | None = None,
        top_n: int | None = None,
    ) -> RetrievalResult:
        effective_filters = filters or RetrievalFilter()
        limit = top_k or self._top_k
        keep = top_n or self._top_n

        vector = await self._embedder.embed_query(query)
        if not vector:
            return RetrievalResult(query=query)

        candidates = await self._store.search(vector, filters=effective_filters, limit=limit)
        if not candidates:
            logger.info("Không tìm thấy chunk nào cho truy vấn")
            return RetrievalResult(query=query)

        chunks = await self._reranker.rerank(query, candidates, keep)
        coverage = max((chunk.score for chunk in chunks), default=0.0)
        return RetrievalResult(
            chunks=chunks,
            coverage=min(max(coverage, 0.0), 1.0),
            query=query,
        )


class EmptyRetriever:
    """Luôn trả về rỗng — dùng khi RAG chưa bật (giai đoạn hiện tại).

    Nhờ có nó, agent chạy đúng nhánh 'chưa đủ dữ liệu' ngay từ bây giờ thay vì
    phải chờ module Data hoàn thiện.
    """

    async def retrieve(
        self,
        query: str,
        *,
        filters: RetrievalFilter | None = None,
        top_k: int | None = None,
        top_n: int | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(query=query)
