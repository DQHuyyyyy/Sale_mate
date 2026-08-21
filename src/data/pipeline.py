"""Pipeline nạp tài liệu: load → chunk → embed → ghi vector store.

Pipeline pattern — thêm/bớt bước (OCR, phát hiện mâu thuẫn, versioning) mà
không phải sửa các bước còn lại.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from src.core.logging import get_logger
from src.data.contracts import Chunk, Chunker, DocumentLoader, Embedder, LoadedDocument, VectorStore

logger = get_logger(__name__)


class IngestReport(BaseModel):
    """Kết quả một lần nạp tài liệu."""

    doc_id: str
    title: str
    chunks: int
    replaced: int = 0

    @property
    def ok(self) -> bool:
        return self.chunks > 0


class IngestPipeline:
    """Nạp một tài liệu vào vector store."""

    def __init__(
        self,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        *,
        loaders: list[DocumentLoader] | None = None,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._loaders = loaders or []

    async def ingest_document(self, document: LoadedDocument) -> IngestReport:
        """Nạp một tài liệu đã parse sẵn."""
        await self._store.ensure_collection(self._embedder.dimension)

        # Upload bản mới thì xoá bản cũ cùng doc_id — chỉ giữ bản đang hiệu lực.
        replaced = await self._store.delete_by_doc(document.doc_id)

        chunks = self._chunker.split(document)
        if not chunks:
            logger.warning("Tài liệu %s không sinh ra chunk nào", document.doc_id)
            return IngestReport(doc_id=document.doc_id, title=document.title, chunks=0)

        # Nhúng KÈM tiêu đề và mục: chunk chứa bảng chiết khấu, tự nó không
        # mang dấu vết nào cho biết thuộc tài liệu "Chính sách bán hàng". Đo
        # được: hỏi đúng tên tài liệu mà nó không lọt nổi top 10.
        # Chỉ ghép vào VĂN BẢN ĐEM NHÚNG, `chunk.text` giữ nguyên để trích dẫn
        # và hiển thị không lẫn phần tiêu đề lặp lại.
        vectors = await self._embedder.embed_texts([_van_ban_nhung(document, c) for c in chunks])
        await self._store.upsert(chunks, vectors)

        return IngestReport(
            doc_id=document.doc_id,
            title=document.title,
            chunks=len(chunks),
            replaced=replaced,
        )

    async def ingest_file(self, path: Path) -> IngestReport:
        """Chọn loader phù hợp rồi nạp file."""
        for loader in self._loaders:
            if loader.can_handle(path):
                document = await loader.load(path)
                return await self.ingest_document(document)
        raise ValueError(f"Chưa có loader nào xử lý được định dạng: {path.suffix}")


def _van_ban_nhung(document: LoadedDocument, chunk: Chunk) -> str:
    """Văn bản dùng để sinh vector — nội dung chunk cộng ngữ cảnh tài liệu."""
    dau = [document.title, str(chunk.metadata.get("section") or "")]
    dau = [d for d in dict.fromkeys(dau) if d]
    return "\n".join([*dau, chunk.text]) if dau else chunk.text
