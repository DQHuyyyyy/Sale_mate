"""VectorStore chạy trong bộ nhớ — mặc định cho dev và test.

Không cần Docker, không cần Qdrant. Dùng cosine similarity thuần Python.
Chỉ hợp cho vài nghìn chunk; production dùng QdrantVectorStore.
"""

from __future__ import annotations

import math

from src.data.contracts import Chunk, RetrievalFilter


class InMemoryVectorStore:
    """Cài đặt VectorStore bằng dict trong RAM."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, list[float]] = {}
        self._dimension: int | None = None

    async def ensure_collection(self, dimension: int) -> None:
        self._dimension = dimension

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("Số chunk và số vector phải bằng nhau")
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = vector
        return len(chunks)

    async def search(
        self,
        vector: list[float],
        *,
        filters: RetrievalFilter,
        limit: int,
    ) -> list[Chunk]:
        scored: list[tuple[float, Chunk]] = []
        for chunk_id, stored in self._vectors.items():
            chunk = self._chunks[chunk_id]
            if not _matches(chunk, filters):
                continue
            scored.append((_cosine(vector, stored), chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk.model_copy(update={"score": score}) for score, chunk in scored[:limit]]

    async def delete_by_doc(self, doc_id: str) -> int:
        targets = [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]
        for chunk_id in targets:
            self._chunks.pop(chunk_id, None)
            self._vectors.pop(chunk_id, None)
        return len(targets)

    async def count(self) -> int:
        return len(self._chunks)


def _matches(chunk: Chunk, filters: RetrievalFilter) -> bool:
    """Áp đúng bộ lọc mà Qdrant sẽ áp — giữ hành vi hai store giống nhau."""
    if chunk.visibility not in filters.visibility:
        return False
    if filters.is_active and not chunk.is_active:
        return False
    if filters.doc_ids is not None and chunk.doc_id not in filters.doc_ids:
        return False
    if filters.project is not None and chunk.metadata.get("project") != filters.project:
        return False
    for key, expected in filters.extra.items():
        if chunk.metadata.get(key) != expected:
            return False
    return True


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
