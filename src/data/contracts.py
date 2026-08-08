"""HỢP ĐỒNG của module DATA — đường GHI dữ liệu.

    crawl → parse → chunk → embed → vector store

Module khác CHỈ import từ file này, không import class cụ thể trong stores/
hay ingestion/. Nhờ vậy đổi Qdrant ↔ Chroma, OpenAI ↔ BGE-M3 không phải sửa
bên gọi.

`RetrievalFilter` nằm ở đây chứ không ở `src/rag/` vì nó là **tham số truy vấn
của VectorStore**. Để bên rag thì data phải import rag, mà rag đã import data
→ vòng lặp. Phần đọc (RetrievalResult · Retriever · Reranker) ở
`src/rag/contracts.py`.

Chủ sở hữu: viet (src/data/**)
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
