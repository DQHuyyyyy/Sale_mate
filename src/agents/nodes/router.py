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

- general: CHỈ dùng cho xã giao — chào hỏi, cảm ơn, tạm biệt, tán gẫu ngoài
  chủ đề bất động sản. Người dùng không hỏi thông tin gì.
- document: cần tra tài liệu dự án — chính sách, ưu đãi, tiện ích, vị trí,
  tiến độ, tổng quan dự án
- listing: tìm bất động sản, tin đăng, so sánh căn
- price: hỏi giá, định giá, mặt bằng giá khu vực
- legal: thủ tục pháp lý, sổ đỏ, hợp đồng, thuế phí
- draft: nhờ soạn nội dung (tin đăng, tin nhắn cho khách)

QUAN TRỌNG: câu hỏi mơ hồ, cụt ngủn, thiếu tên dự án hay tiêu chí VẪN là câu
hỏi thông tin — chọn nhãn theo chủ đề, KHÔNG chọn general. "Ocean Park có ưu
đãi gì" là document, không phải general.

Chỉ trả về đúng một từ nhãn, không giải thích gì thêm.

Câu hỏi: {query}"""

# Luật nhanh: từ khoá rõ ràng thì khỏi tốn một lượt gọi LLM.
_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.LEGAL, ("sổ đỏ", "sổ hồng", "pháp lý", "thủ tục", "hợp đồng", "thuế", "sang tên")),
    (Intent.PRICE, ("giá", "bao nhiêu tiền", "định giá", "tr/m2", "tr/m²")),
    (Intent.DRAFT, ("viết tin", "soạn tin", "viết giúp", "soạn giúp", "tiêu đề tin")),
    (Intent.LISTING, ("tìm căn", "tìm nhà", "tìm mua", "căn hộ", "nhà phố", "đất nền")),
]


# Nhãn KHÔNG cần tra tài liệu. Khai theo hướng loại trừ, không phải liệt kê
# nhãn được phép — đảo chiều mặc định là chỗ sửa quan trọng nhất của node này.
#
# Trước đây `needs_retrieval` chỉ bật cho {DOCUMENT, LEGAL, PRICE}, nên `general`
# thành ngõ cụt tuyệt đối: không truy hồi, không tool, `plan` nhận state rỗng và
# nước duy nhất còn lại là hỏi ngược người dùng. Đo được trên câu thật: "Ocean
# park có ưu đãi gì" bị xếp `general` → trợ lý hỏi lại, trong khi truy hồi cho
# độ phủ 0.919 với đúng hai tài liệu ưu đãi OP2 và OP3.
#
# Nghịch lý của cách cũ: câu càng mơ hồ càng cần tra cứu thì càng bị từ chối tra
# cứu. Nay chỉ xã giao và soạn nội dung mới bỏ qua truy hồi; thêm nhãn mới về
# sau là tự động được tra cứu, tức là mặc định an toàn.
_KHONG_TRA_CUU = {Intent.GENERAL, Intent.DRAFT}


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
            "needs_retrieval": intent not in _KHONG_TRA_CUU,
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
