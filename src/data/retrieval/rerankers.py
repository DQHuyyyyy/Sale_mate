"""Reranker — xếp lại top-k trước khi đưa vào LLM.

PassthroughReranker là mặc định hiện tại: giữ nguyên thứ tự của vector search.
bge-reranker-v2-m3 sẽ thay vào sau (cần requirements-ml.txt) mà không đổi bên gọi.
"""

from __future__ import annotations

from src.data.contracts import Chunk, Reranker  # noqa: F401


class PassthroughReranker:
    """Không xếp lại, chỉ cắt lấy top-n. Dùng khi chưa bật reranker thật."""

    async def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        return chunks[:top_n]


class KeywordOverlapReranker:
    """Reranker nhẹ: cộng điểm cho chunk chứa nhiều từ khoá của câu hỏi.

    Không thay được model rerank thật, nhưng đủ để thấy hiệu ứng rerank trong
    eval trước khi có GPU/API.
    """

    def __init__(self, weight: float = 0.3) -> None:
        self._weight = weight

    async def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        terms = {token for token in query.lower().split() if len(token) > 2}
        if not terms:
            return chunks[:top_n]

        rescored: list[Chunk] = []
        for chunk in chunks:
            text = chunk.text.lower()
            hits = sum(1 for term in terms if term in text)
            bonus = self._weight * (hits / len(terms))
            rescored.append(chunk.model_copy(update={"score": chunk.score + bonus}))

        rescored.sort(key=lambda chunk: chunk.score, reverse=True)
        return rescored[:top_n]
