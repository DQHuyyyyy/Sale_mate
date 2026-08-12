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
from src.models.chat import Citation

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
        # Agent chủ động hỏi lại thì câu trả lời VỐN LÀ một câu hỏi — thiếu dữ
        # liệu là chuyện đương nhiên, không được thay bằng thông điệp từ chối.
        if state.get("plan_action") == "clarify":
            return {"is_sensitive": False, "citations": []}

        if state.get("needs_retrieval") and not self._has_enough_context(state):
            return {
                "answer": INSUFFICIENT_MESSAGE,
                "citations": [],
                "is_sensitive": False,
            }

        return {
            "is_sensitive": self._is_sensitive(state),
            "citations": self._all_citations(state),
        }

    def _has_enough_context(self, state: AgentState) -> bool:
        """Đủ dữ liệu khi truy hồi đạt ngưỡng, HOẶC khi tool đã trả về số liệu.

        Không tính kết quả tool là bỏ sót trường hợp hay gặp nhất: hỏi giá một
        căn cụ thể. Nhãn đó bật needs_retrieval, mà kho tài liệu không chứa giá
        từng căn — độ phủ luôn dưới ngưỡng. Thiếu vế sau thì agent từ chối trả
        lời ngay cả khi tool đã cầm sẵn con số đúng trong tay.
        """
        if state.get("tool_context"):
            return True
        return bool(state.get("chunks")) and state.get("coverage", 0.0) >= self._threshold

    def _all_citations(self, state: AgentState) -> list[Citation]:
        """Gộp nguồn tài liệu với nguồn tool.

        Gộp ở đây vì guardrail là node cuối: node retrieve chạy sau tools và
        ghi đè `citations`, nên tool phải giữ nguồn của mình ở khoá riêng cho
        tới bước này.
        """
        return [*state.get("citations", []), *state.get("tool_citations", [])]

    def _is_sensitive(self, state: AgentState) -> bool:
        answer = state.get("answer", "")
        if not answer:
            return False
        has_price = bool(_PRICE_PATTERN.search(answer))
        has_commitment = any(word in answer.lower() for word in _COMMITMENT_WORDS)
        return (has_price and has_commitment) or state.get("intent") == Intent.DRAFT
