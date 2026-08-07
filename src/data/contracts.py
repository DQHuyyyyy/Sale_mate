"""HỢP ĐỒNG của module Data (RAG).

Module khác (agents, api) CHỈ import từ file này — không import class cụ thể
trong stores/ hay embedders/. Nhờ vậy đổi Qdrant ↔ Chroma, OpenAI ↔ BGE-M3
không cần sửa bên gọi.

Chủ sở hữu: dat (src/data/**)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, cast, runtime_checkable

from pydantic import BaseModel, Field

Visibility = Literal["public", "internal"]


class Chunk(BaseModel):
    """Một đoạn văn bản đã tách, kèm metadata đủ để trích nguồn."""

    id: str
    text: str
    doc_id: str
    doc_title: str = ""
    version: str = ""
    page: int | None = None
    section: str = ""
    visibility: Visibility = "public"
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(default=0.0, description="Điểm liên quan sau search/rerank")


class LoadedDocument(BaseModel):
    """Kết quả parse một file trước khi chunk."""

    doc_id: str
    title: str
    text: str
    source_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalFilter(BaseModel):
    """Điều kiện lọc áp NGAY tại truy vấn vector (Hybrid filtering).

    Phân quyền và bộ lọc cấu trúc (bất động sản) phải lọc ở đây trước khi rank vector.
    """

    visibility: list[Visibility] = Field(default_factory=lambda: [cast(Visibility, "public")])
    is_active: bool = True
    project: str | None = None
    doc_ids: list[str] | None = None
    # Lọc cấu trúc bất động sản (phân biệt với tìm kiếm ngữ nghĩa)
    min_price: float | None = Field(default=None, description="Giá tối thiểu (VNĐ hoặc tỷ)")
    max_price: float | None = Field(default=None, description="Giá tối đa (VNĐ hoặc tỷ)")
    min_area: float | None = Field(default=None, description="Diện tích tối thiểu (m²)")
    max_area: float | None = Field(default=None, description="Diện tích tối đa (m²)")
    num_bedrooms: int | None = Field(default=None, description="Số phòng ngủ / phòng")
    building: str | None = Field(default=None, description="Tòa (ví dụ: S1.01, Tòa A)")
    property_type: str | None = Field(default=None, description="Loại căn (ví dụ: 1PN+, Studio, Chung cư)")
    doc_kind: str | None = Field(default=None, description="Loại tài liệu: 'listing' hoặc 'policy'")
    extra: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Kết quả truy hồi kèm độ phủ để quyết định có đủ dữ liệu trả lời không."""

    chunks: list[Chunk] = Field(default_factory=list)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    query: str = ""

    def is_sufficient(self, threshold: float) -> bool:
        """Dưới ngưỡng thì agent phải trả lời 'chưa đủ dữ liệu'."""
        return bool(self.chunks) and self.coverage >= threshold

    def as_context(self, separator: str = "\n---\n") -> str:
        """Ghép các chunk Reranked thành context giàu metadata đưa vào LLM Prompt."""
        pieces: list[str] = []
        for chunk in self.chunks:
            meta = chunk.metadata
            piece = chunk.text
            extra_details: list[str] = []
            if "ma_can" in meta and meta["ma_can"]:
                extra_details.append(f"Mã căn: [{meta['ma_can']}]")
            if "image_url" in meta and meta["image_url"]:
                extra_details.append(f"Link Ảnh: {meta['image_url']}")
            if "price" in meta and meta["price"]:
                orig = meta["price"]
                disc = round(orig * 0.92, 3)
                extra_details.append(f"Giá gốc: {orig} tỷ (Giá sau chiết khấu 8%: {disc} tỷ)")
            if extra_details:
                piece += "\n[Chi tiết bổ sung: " + " | ".join(extra_details) + "]"
            pieces.append(piece)
        return separator.join(pieces)


# --------------------------------------------------------------------------
# Protocol — mỗi cái là một điểm cắm implementation
# --------------------------------------------------------------------------


@runtime_checkable
class DocumentLoader(Protocol):
    """Đọc một file (PDF/Excel/ảnh/text) thành văn bản có metadata."""

    def can_handle(self, path: Path) -> bool: ...

    async def load(self, path: Path) -> LoadedDocument: ...


@runtime_checkable
class Chunker(Protocol):
    """Tách văn bản thành chunk. Strategy — thay được để A/B test chunking."""

    def split(self, document: LoadedDocument) -> list[Chunk]: ...


@runtime_checkable
class Embedder(Protocol):
    """Sinh vector. Cùng một Embedder phải dùng cho cả ingest và query."""

    @property
    def dimension(self) -> int: ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Repository cho vector + metadata."""

    async def ensure_collection(self, dimension: int) -> None: ...

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int: ...

    async def search(
        self,
        vector: list[float],
        *,
        filters: RetrievalFilter,
        limit: int,
    ) -> list[Chunk]: ...

    async def delete_by_doc(self, doc_id: str) -> int: ...

    async def count(self) -> int: ...


@runtime_checkable
class Reranker(Protocol):
    """Xếp lại kết quả trước khi đưa vào LLM."""

    async def rerank(self, query: str, chunks: list[Chunk], top_n: int) -> list[Chunk]: ...


@runtime_checkable
class Retriever(Protocol):
    """Mặt tiền cho toàn bộ khâu truy hồi — agent chỉ gọi cái này."""

    async def retrieve(
        self,
        query: str,
        *,
        filters: RetrievalFilter | None = None,
        top_k: int | None = None,
        top_n: int | None = None,
    ) -> RetrievalResult: ...
