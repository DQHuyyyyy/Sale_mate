"""Reranker — xếp lại top-k ứng viên trước khi đưa vào LLM Prompt.

- PassthroughReranker: Giữ nguyên thứ tự của Vector Search (dùng mặc định nhẹ).
- KeywordOverlapReranker: Reranker nhẹ cộng điểm dựa trên từ khóa từ câu hỏi.
- CrossEncoderReranker: Reranker chuẩn dùng Cross-Encoder model (BAAI/bge-reranker-v2-m3 hoặc ms-marco-MiniLM-L-6-v2) để chấm điểm cặp (query, chunk.text).
- FakeCrossEncoderReranker: Mock Reranker phục vụ unit test và dev nhanh không tốn GPU/RAM.
"""

from __future__ import annotations

import math
from typing import Any

from src.data.contracts import Chunk  # noqa: F401


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


class CrossEncoderReranker:
    """Reranker sử dụng mô hình Cross-Encoder (như BAAI/bge-reranker-v2-m3 hoặc ms-marco-MiniLM-L-6-v2).

    Chấm điểm trực tiếp cặp (query, chunk.text) để xếp hạng lại top-k ứng viên từ Qdrant,
    chắt lọc lấy top-n (ví dụ top_n=3) tinh túy nhất cho Prompt Context.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name)
            except ImportError as exc:
                raise ImportError(
                    "Cần cài đặt sentence-transformers để dùng CrossEncoderReranker thực tế: "
                    "pip install sentence-transformers"
                ) from exc
        return self._model

    async def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        if not chunks:
            return []
        if top_n <= 0:
            return []

        model = self._get_model()
        pairs = [(query, chunk.text) for chunk in chunks]
        scores = model.predict(pairs)

        rescored: list[Chunk] = []
        for chunk, raw_score in zip(chunks, scores, strict=True):
            score_val = float(raw_score) if isinstance(raw_score, (int, float)) else float(raw_score[0])
            norm_score = float(1.0 / (1.0 + math.exp(-score_val)))
            rescored.append(chunk.model_copy(update={"score": round(norm_score, 4)}))

        rescored.sort(key=lambda c: c.score, reverse=True)
        return rescored[:top_n]


class FakeCrossEncoderReranker:
    """Mock Cross-Encoder Reranker phục vụ unit test và dev không tốn GPU/RAM."""

    async def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]:
        if not chunks:
            return []
        terms = {t.lower() for t in query.split() if len(t) > 1}
        rescored: list[Chunk] = []

        for chunk in chunks:
            text_lower = chunk.text.lower()
            overlap = sum(1 for term in terms if term in text_lower)
            rerank_score = chunk.score * 0.4 + (overlap / max(len(terms), 1)) * 0.6
            rescored.append(chunk.model_copy(update={"score": round(rerank_score, 4)}))

        rescored.sort(key=lambda c: c.score, reverse=True)
        return rescored[:top_n]
