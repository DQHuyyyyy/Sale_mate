"""Node guardrail — chặn hai thứ trước khi trả về người dùng.

1. Độ phủ thấp → thay câu trả lời bằng thông điệp "chưa đủ dữ liệu" thay vì để
   LLM suy đoán. Đây là nguyên tắc "biết dừng".
2. Đánh dấu nội dung nhạy cảm (có giá cụ thể + ngữ cảnh cam kết/gửi khách) để
   tầng trên quyết định có cần người duyệt không.
"""

from __future__ import annotations

import re
from typing import Any

from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState, Intent

INSUFFICIENT_MESSAGE = (
    "Mình chưa có đủ dữ liệu để trả lời chính xác câu này. "
    "Bạn cho mình biết thêm khu vực, dự án hoặc mức ngân sách để tra cứu sát hơn nhé."
)

# Con số kèm đơn vị tiền/diện tích — dấu hiệu của thông tin có hệ quả.
_PRICE_PATTERN = re.compile(r"\d[\d.,]*\s*(tỷ|triệu|tr/m²|tr/m2|đồng|vnđ)", re.IGNORECASE)
_COMMITMENT_WORDS = (
    "cam kết",
    "giữ chỗ",
    "đặt cọc",
    "ưu đãi",
    "chiết khấu",
    "gửi khách",
    "chốt giá",
)


class GuardrailNode(BaseNode):
    """Kiểm tra độ phủ và gắn cờ nhạy cảm."""

    name = "guardrail"

    def __init__(self, coverage_threshold: float) -> None:
        self._threshold = coverage_threshold

    async def execute(self, state: AgentState) -> dict[str, Any]:
        updates: dict[str, Any] = {}

        if state.get("needs_retrieval") and not self._has_enough_context(state):
            return {
                "answer": INSUFFICIENT_MESSAGE,
                "citations": [],
                "is_sensitive": False,
            }

        updates["is_sensitive"] = self._is_sensitive(state)
        return updates

    def _has_enough_context(self, state: AgentState) -> bool:
        return bool(state.get("chunks")) and state.get("coverage", 0.0) >= self._threshold

    def _is_sensitive(self, state: AgentState) -> bool:
        answer = state.get("answer", "")
        if not answer:
            return False
        has_price = bool(_PRICE_PATTERN.search(answer))
        has_commitment = any(word in answer.lower() for word in _COMMITMENT_WORDS)
        return (has_price and has_commitment) or state.get("intent") == Intent.DRAFT
