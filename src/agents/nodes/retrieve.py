"""Node truy hồi tài liệu.

Node này không biết gì về Qdrant hay embedding — nó chỉ gọi Retriever Protocol.
Đó là lý do module Data đổi thoải mái mà AI_core không phải sửa.
"""

from __future__ import annotations

from typing import Any

from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState, Intent
from src.data.contracts import RetrievalFilter
from src.models.chat import Citation
from src.rag.contracts import Retriever

# Nhãn nào thì chỉ nên đọc tài liệu chính sách, không đọc tin rao vặt.
#
# Vì sao cần: kho vector có 864 chunk tin rao ("Chính chủ cần bán…") và chỉ 66
# chunk chính sách. Hỏi "chính sách bán hàng chiết khấu" thì cả ba kết quả đầu
# đều là tin rao — chúng dùng chung từ vựng ("chính chủ", "bán", "thanh toán")
# và đông gấp 13 lần nên luôn thắng. Tài liệu tên đúng y câu hỏi không lọt nổi
# vào top.
#
# Độ phủ vẫn cao trong ca đó, nên guardrail không chặn: câu trả lời đi tiếp với
# ngữ cảnh sai và model đành nói "chưa đủ dữ liệu". Hỏng câm, không báo lỗi.
_CHI_DOC_CHINH_SACH = {Intent.LEGAL, Intent.DOCUMENT}


class RetrieveNode(BaseNode):
    """Lấy chunk liên quan và tính độ phủ."""

    name = "retrieve"

    def __init__(self, retriever: Retriever, *, visibility: list[str] | None = None) -> None:
        self._retriever = retriever
        self._visibility = visibility or ["public"]

    async def execute(self, state: AgentState) -> dict[str, Any]:
        if not state.get("needs_retrieval"):
            return {"chunks": [], "coverage": 0.0, "context": ""}

        result = await self._retriever.retrieve(
            state.get("query", ""),
            filters=RetrievalFilter(
                visibility=self._visibility,  # type: ignore[arg-type]
                doc_kind="policy" if state.get("intent") in _CHI_DOC_CHINH_SACH else None,
            ),
        )

        return {
            "chunks": result.chunks,
            "coverage": result.coverage,
            "context": result.as_context(),
            "citations": [
                Citation(
                    doc_id=chunk.doc_id,
                    title=chunk.doc_title or chunk.doc_id,
                    version=chunk.version,
                    page=chunk.page,
                    section=chunk.section,
                    kind="doc",
                )
                for chunk in result.chunks
            ],
        }
