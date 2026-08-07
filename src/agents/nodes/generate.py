"""Node sinh câu trả lời cuối — dùng model MẠNH.

Nếu có context truy hồi thì ép LLM chỉ dựa vào context đó (grounding).
Nếu không có, LLM trả lời theo kiến thức chung nhưng vẫn bị prompt cấm bịa số.
"""

from __future__ import annotations

from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.base import BaseNode
from src.agents.prompts import system_prompt
from src.agents.state import AgentState
from src.models.chat import ChatMessage, MessageRole

_GROUNDED_TEMPLATE = """Dựa DUY NHẤT vào ngữ cảnh dưới đây để trả lời. \
Nếu ngữ cảnh không chứa thông tin cần thiết hoặc thông tin chưa đủ, tuyệt đối không tự suy đoán hay bịa đặt số liệu (giá, diện tích, vị trí, pháp lý), hãy nói rõ là chưa có đủ dữ liệu. \
Mọi thông tin về căn hộ hoặc chính sách ĐỀU BẮT BUỘC phải trích dẫn nguồn bằng định dạng [Mã căn] hoặc [Tên tài liệu] ngay sau khẳng định đó.

<ngu_canh>
{context}
</ngu_canh>

Câu hỏi: {query}"""


def build_messages(state: AgentState) -> list[ChatMessage]:
    """Ghép system prompt + lịch sử + câu hỏi (kèm context nếu có).

    Tách riêng để tầng streaming dùng lại được đúng cách dựng prompt này.
    """
    messages: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=system_prompt())]
    messages.extend(state.get("history", []))

    query = state.get("query", "")
    context = state.get("context", "")
    content = _GROUNDED_TEMPLATE.format(context=context, query=query) if context else query
    messages.append(ChatMessage(role=MessageRole.USER, content=content))
    return messages


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
