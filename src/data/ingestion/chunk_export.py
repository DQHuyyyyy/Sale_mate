"""Xuất chunk ra JSON tường minh trước khi embed.

Đúng bước "Chunking -> JSON chứa chunk" trong luồng xử lý dữ liệu — tách bạch
khỏi bước Embedding, dùng chung cho mọi script ingest thay vì giấu bên trong
`IngestPipeline` (vốn gộp chunk+embed+upsert làm một, không lộ ra JSON trung
gian để đối chiếu).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data.contracts import Chunk, Chunker, LoadedDocument


def _chunk_to_dict(chunk: Chunk) -> dict:
    return {
        "id": chunk.id,
        "doc_id": chunk.doc_id,
        "doc_title": chunk.doc_title,
        "section": chunk.section,
        "visibility": chunk.visibility,
        "version": chunk.version,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


def chunk_and_export_json(documents: list[LoadedDocument], chunker: Chunker, json_path: Path) -> list[Chunk]:
    """Chunk toàn bộ tài liệu, ghi ra file JSON, trả về danh sách chunk để
    bước Embedding dùng tiếp.
    """
    all_chunks: list[Chunk] = []
    for document in documents:
        all_chunks.extend(chunker.split(document))

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps([_chunk_to_dict(chunk) for chunk in all_chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return all_chunks
