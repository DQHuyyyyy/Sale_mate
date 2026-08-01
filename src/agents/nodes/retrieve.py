"""Node truy hồi tài liệu.

Node này không biết gì về Qdrant hay embedding — nó chỉ gọi Retriever Protocol.
Đó là lý do module Data đổi thoải mái mà AI_core không phải sửa.
"""

from __future__ import annotations

from typing import Any

from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.data.contracts import RetrievalFilter, Retriever
from src.models.chat import Citation


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
            filters=RetrievalFilter(visibility=self._visibility),  # type: ignore[arg-type]
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
