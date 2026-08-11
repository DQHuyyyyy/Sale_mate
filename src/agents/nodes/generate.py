"""Node sinh câu trả lời cuối — dùng model MẠNH.

Node chỉ điều phối: lấy prompt từ `src/rag/grounding.py` rồi gọi LLM. Cách dựng
prompt (grounding, chống injection, quy tắc trích nguồn) thuộc module RAG.
"""

from __future__ import annotations

from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.base import BaseNode
from src.agents.prompts import system_prompt
from src.agents.state import AgentState
from src.models.chat import ChatMessage
from src.rag.grounding import build_grounded_messages


def merged_context(state: AgentState) -> str:
    """Ghép dữ liệu tool với tài liệu truy hồi.

    Tool đứng TRƯỚC: đó là số liệu đọc thẳng từ nguồn sự thật ngay lúc hỏi, còn
    tài liệu trong vector store là bản chụp. Khi hai nguồn nói khác nhau về giá
    hay tình trạng căn, cái đúng phải nằm ở vị trí model đọc trước.
    """
    parts = [state.get("tool_context", ""), state.get("context", "")]
    return "\n\n".join(part for part in parts if part)


def build_messages(state: AgentState) -> list[ChatMessage]:
    """Dựng prompt từ state.

    Tách riêng để tầng streaming (`agents/service.py`) dùng lại đúng cách dựng
    prompt này, không tự ghép lần nữa.
    """
    return build_grounded_messages(
        state.get("query", ""),
        system_prompt=system_prompt(),
        context=merged_context(state),
        history=state.get("history", []),
    )


class GenerateNode(BaseNode):
    """Sinh câu trả lời."""

    name = "generate"

    def __init__(
        self,
        llm: LLMProvider,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def execute(self, state: AgentState) -> dict[str, Any]:
        answer = await self._llm.complete(
            build_messages(state),
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return {"answer": answer.strip()}
