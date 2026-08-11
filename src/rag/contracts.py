"""HỢP ĐỒNG của module RAG — đường ĐỌC dữ liệu.

    câu hỏi → embed → search (lọc quyền) → rerank → grounding

Tầng agent chỉ import `Retriever` từ đây; nó không biết Qdrant, embedding hay
rerank model nào đang chạy.

Phân chia với `src/data/contracts.py`:

    data/  Chunk · LoadedDocument · Embedder · VectorStore · RetrievalFilter
    rag/   RetrievalResult · Retriever · Reranker

`RetrievalFilter` ở bên data vì nó là tham số truy vấn của `VectorStore.search()`
— để bên này thì data phải import rag, tạo vòng lặp. Phụ thuộc chỉ đi một
chiều: rag → data.

Chủ sở hữu: phuc (src/rag/**)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.data.contracts import Chunk, RetrievalFilter


class RetrievalResult(BaseModel):
    """Kết quả truy hồi kèm độ phủ để quyết định có đủ dữ liệu trả lời không."""

    chunks: list[Chunk] = Field(default_factory=list)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    query: str = ""

    def is_sufficient(self, threshold: float) -> bool:
        """Dưới ngưỡng thì agent phải trả lời 'chưa đủ dữ liệu'."""
        return bool(self.chunks) and self.coverage >= threshold

    def as_context(self, separator: str = "\n---\n") -> str:
        """Ghép chunk đã rerank thành context đưa vào prompt.

        Chỉ chuyển tiếp những gì CÓ TRONG tài liệu. Không tính toán, không suy
        diễn, không thêm số nào không tồn tại trong metadata.

        Trước đây hàm này tự tính "giá sau chiết khấu 8%" từ một mức hardcode.
        Con số đó không có trong tài liệu nào, nhưng LLM đọc thấy rồi nhắc lại
        như thể là chính sách công ty. Đã bỏ hẳn.

        Muốn nêu chiết khấu thì mức chiết khấu phải là **dữ liệu có nguồn** —
        nằm trong tài liệu chính sách đã ingest, hoặc lấy qua tool tra DB — chứ
        không phải hằng số trong code.
        """
        pieces: list[str] = []
        for chunk in self.chunks:
            meta = chunk.metadata
            details: list[str] = []
            if meta.get("ma_can"):
                details.append(f"Mã căn: [{meta['ma_can']}]")
            if meta.get("image_url"):
                details.append(f"Link ảnh: {meta['image_url']}")
            if meta.get("price"):
                details.append(f"Giá: {meta['price']}")

            piece = chunk.text
            if details:
                piece += "\n[Chi tiết bổ sung: " + " | ".join(details) + "]"
            pieces.append(piece)
        return separator.join(pieces)


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
