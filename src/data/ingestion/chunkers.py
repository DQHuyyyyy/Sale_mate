"""Chunker — tách tài liệu thành đoạn trước khi embed.

Strategy pattern: mọi chunker cùng tuân Chunker Protocol, đổi được để A/B test
ảnh hưởng của chunking lên điểm eval mà không sửa pipeline.
"""

from __future__ import annotations

import re

from src.data.contracts import Chunk, Chunker, LoadedDocument  # noqa: F401

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


class ParagraphChunker:
    """Tách theo đoạn, gộp lại cho đủ kích thước mục tiêu.

    Tôn trọng ranh giới đoạn nên không cắt vỡ bảng biểu giữa chừng.
    """

    def __init__(self, target_chars: int = 900, overlap_chars: int = 120) -> None:
        if overlap_chars >= target_chars:
            raise ValueError("overlap_chars phải nhỏ hơn target_chars")
        self._target = target_chars
        self._overlap = overlap_chars

    def split(self, document: LoadedDocument) -> list[Chunk]:
        paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(document.text) if p.strip()]
        if not paragraphs:
            return []

        pieces: list[str] = []
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if len(candidate) <= self._target:
                buffer = candidate
                continue

            tail = buffer[-self._overlap :] if buffer and self._overlap else ""
            if buffer:
                pieces.append(buffer)

            # Đoạn mới (kể cả cộng thêm tail overlap) có thể vẫn vượt target —
            # phải cắt cứng ngay, không được gán thẳng làm buffer mới, nếu
            # không chunk cuối cùng sẽ phình to hơn target nhiều lần.
            merged = f"{tail}\n\n{paragraph}" if tail else paragraph
            if len(merged) <= self._target:
                buffer = merged
            else:
                *full_pieces, buffer = self._hard_split(merged)
                pieces.extend(full_pieces)
        if buffer:
            pieces.append(buffer)

        return [
            Chunk(
                id=f"{document.doc_id}::{index}",
                text=piece,
                doc_id=document.doc_id,
                doc_title=document.title,
                version=str(document.metadata.get("version", "")),
                section=str(document.metadata.get("section", "")),
                visibility=document.metadata.get("visibility", "public"),
                metadata=document.metadata,
            )
            for index, piece in enumerate(pieces)
        ]

    def _hard_split(self, text: str) -> list[str]:
        """Đoạn dài hơn target thì cắt cứng theo độ dài."""
        step = self._target - self._overlap
        return [text[start : start + self._target] for start in range(0, len(text), step)]
