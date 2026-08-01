"""Node phân loại câu hỏi (router).

Dùng model RẺ vì đây là bước nằm trên đường tới độ trễ cảm nhận của người dùng.
Có luật ưu tiên trước, chỉ gọi LLM khi luật không quyết được — vừa nhanh vừa rẻ.
"""

from __future__ import annotations

from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState, Intent
from src.core.logging import get_logger
from src.models.chat import ChatMessage, MessageRole

logger = get_logger(__name__)

_ROUTER_PROMPT = """Phân loại câu hỏi của người dùng vào ĐÚNG MỘT nhãn sau:

- general: chào hỏi, hỏi vu vơ, không cần tra cứu
- document: cần tra tài liệu dự án, chính sách, tiện ích
- listing: tìm bất động sản, tin đăng, so sánh căn
- price: hỏi giá, định giá, mặt bằng giá khu vực
- legal: thủ tục pháp lý, sổ đỏ, hợp đồng, thuế phí
- draft: nhờ soạn nội dung (tin đăng, tin nhắn cho khách)

Chỉ trả về đúng một từ nhãn, không giải thích gì thêm.

Câu hỏi: {query}"""

# Luật nhanh: từ khoá rõ ràng thì khỏi tốn một lượt gọi LLM.
_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.LEGAL, ("sổ đỏ", "sổ hồng", "pháp lý", "thủ tục", "hợp đồng", "thuế", "sang tên")),
    (Intent.PRICE, ("giá", "bao nhiêu tiền", "định giá", "tr/m2", "tr/m²")),
    (Intent.DRAFT, ("viết tin", "soạn tin", "viết giúp", "soạn giúp", "tiêu đề tin")),
    (Intent.LISTING, ("tìm căn", "tìm nhà", "tìm mua", "căn hộ", "nhà phố", "đất nền")),
]


class RouterNode(BaseNode):
    """Xác định intent và có cần truy hồi tài liệu không."""

    name = "router"

    def __init__(self, llm: LLMProvider, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def execute(self, state: AgentState) -> dict[str, Any]:
        query = state.get("query", "")
        intent = self._match_keywords(query) or await self._classify(query)
        return {
            "intent": intent,
            "needs_retrieval": intent in {Intent.DOCUMENT, Intent.LEGAL, Intent.PRICE},
        }

    def _match_keywords(self, query: str) -> Intent | None:
        lowered = query.lower()
        for intent, keywords in _KEYWORD_RULES:
            if any(keyword in lowered for keyword in keywords):
                return intent
        return None

    async def _classify(self, query: str) -> Intent:
        messages = [ChatMessage(role=MessageRole.USER, content=_ROUTER_PROMPT.format(query=query))]
        raw = await self._llm.complete(messages, model=self._model, temperature=0.0, max_tokens=10)
        label = raw.strip().lower().strip(".")
        try:
            return Intent(label)
        except ValueError:
            logger.warning("Router trả nhãn lạ %r, rơi về general", label)
            return Intent.GENERAL
