"""Node lập kế hoạch — nơi agent tự quyết làm gì tiếp theo.

Đây là thứ biến hệ thống từ "pipeline RAG có tool" thành agent thật: model nhìn
câu hỏi cùng những gì đã thu được, rồi chọn một trong ba hành động. Chạy lại sau
mỗi lần hành động, nên nó vừa là bước quan sát vừa là bước quyết định — đúng
kiểu observe-then-decide, không tách thành hai node cho một việc.

    act      gọi thêm một tool để lấy dữ kiện còn thiếu
    clarify  câu hỏi mơ hồ, hỏi lại người dùng thay vì đoán
    answer   đã đủ, chuyển sang sinh câu trả lời

Ba thứ giữ cho nó không chạy loạn:

1. **Trần cứng.** Hết `agent_max_iterations` là ép `answer`, model không có
   quyền xin thêm. Thiếu cái này thì một câu hỏi xấu gọi tool đến hết quota.
2. **Không gọi được tool lạ.** Tên tool model trả về phải có trong registry,
   sai thì rơi về `answer` chứ không thử đoán.
3. **Không lặp lại chính mình.** Hành động trùng với thứ đã thử là dấu hiệu
   agent kẹt — gọi lại cũng ra kết quả cũ, nên cắt sớm thay vì đốt nốt trần.

`LLMProvider` là contract đóng băng và không có API tool-calling, nên plan yêu
cầu model trả JSON qua `complete()` rồi tự parse — cùng cách RouterNode lấy nhãn.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.act import _chu_ky, _lam_sach
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.logging import get_logger

logger = get_logger(__name__)

ACT = "act"
ANSWER = "answer"
CLARIFY = "clarify"

_PROMPT = """Bạn là bộ điều phối của trợ lý bán căn hộ. Chọn ĐÚNG MỘT hành động tiếp theo.

Câu hỏi của người dùng:
{query}

Dữ kiện đã thu thập được:
{evidence}

Các tool có thể gọi:
{tools}

Hành động cho phép:
- "act": còn thiếu dữ kiện và có tool lấy được. Phải nêu "tool" và "args".
- "clarify": câu hỏi quá mơ hồ để tra cứu (thiếu mã căn, thiếu tiêu chí). Nêu câu hỏi ngược lại ở "reason".
- "answer": đã đủ dữ kiện, hoặc không tool nào giúp được.

Trả về DUY NHẤT một object JSON, không giải thích, không bọc trong markdown:
{{"action": "...", "tool": "...", "args": {{}}, "reason": "một câu ngắn bằng tiếng Việt"}}"""

# Model hay bọc JSON trong ```json ... ``` dù đã dặn đừng.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _describe_tools(registry: ToolRegistry) -> str:
    lines = []
    for tool in registry.all():
        schema = (tool.args_schema.model_json_schema() if tool.args_schema else {}) or {}
        params = ", ".join((schema.get("properties") or {}).keys()) or "không có"
        lines.append(f"- {tool.name}: {tool.description}\n  Tham số: {params}")
    return "\n".join(lines) or "(không có tool nào)"


def _describe_evidence(state: AgentState) -> str:
    parts = []
    if state.get("tool_context"):
        parts.append(f"Từ tool:\n{state['tool_context']}")
    if state.get("chunks"):
        parts.append(f"Từ tài liệu: {len(state['chunks'])} đoạn đã truy hồi.")
    return "\n\n".join(parts) or "(chưa có gì)"


class PlanNode(BaseNode):
    """Chọn hành động tiếp theo cho agent."""

    name = "plan"

    def __init__(
        self,
        llm: LLMProvider,
        *,
        max_iterations: int,
        model: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._llm = llm
        self._max_iterations = max_iterations
        self._model = model
        self._registry = registry or default_registry

    async def execute(self, state: AgentState) -> dict[str, Any]:
        iterations = int(state.get("iterations", 0))

        if iterations >= self._max_iterations:
            logger.info("Hết trần %s vòng, ép trả lời", self._max_iterations)
            return self._quyet(ANSWER, "Đã đủ số lần tra cứu cho phép.")

        # CỐ Ý KHÔNG có đường tắt kiểu "tool tất định đã chạy ⇒ trả lời luôn".
        # Từng có, và nó vô hiệu hoá chính vòng lặp: "so sánh căn VOP345 và
        # VOP397" thì ToolsNode chỉ bắt được mã đầu tiên, plan thấy đã có dữ
        # liệu nên dừng — trả lời về một căn rồi im, không bao giờ tra căn thứ
        # hai. Đổi lại mỗi câu hỏi tốn một lượt gọi model rẻ; đó là giá của việc
        # để agent tự quyết, và chỉ phải trả khi `enable_agent_loop` bật.
        raw = await self._llm.complete([self._prompt(state)], model=self._model, temperature=0.0, max_tokens=200)
        return self._doc_ket_qua(raw, state)

    def _prompt(self, state: AgentState):
        from src.models.chat import ChatMessage, MessageRole

        return ChatMessage(
            role=MessageRole.USER,
            content=_PROMPT.format(
                query=state.get("query", ""),
                evidence=_describe_evidence(state),
                tools=_describe_tools(self._registry),
            ),
        )

    def _doc_ket_qua(self, raw: str, state: AgentState) -> dict[str, Any]:
        """Parse JSON model trả về. Hỏng kiểu gì cũng rơi về `answer`.

        Không đoán ý model: kế hoạch đọc không ra thì trả lời bằng những gì đang
        có, còn hơn gọi nhầm tool rồi báo số sai cho khách.
        """
        match = _JSON_BLOCK.search(raw or "")
        if match is None:
            logger.warning("Plan không trả JSON, rơi về answer")
            return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

        try:
            data = json.loads(match.group(0))
        except ValueError:
            logger.warning("Plan trả JSON hỏng, rơi về answer")
            return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

        action = str(data.get("action", "")).strip().lower()
        reason = str(data.get("reason", "")).strip()

        if action == CLARIFY:
            return self._quyet(CLARIFY, reason or "Bạn cho mình thêm thông tin để tra cứu chính xác nhé.")

        if action == ACT:
            tool = str(data.get("tool", "")).strip()
            if self._registry.get(tool) is None:
                logger.warning("Plan chọn tool không có trong registry: %r", tool)
                return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

            args = data.get("args")
            args = args if isinstance(args, dict) else {}

            # Đã thử đúng hành động này rồi mà vẫn quay lại xin nữa nghĩa là
            # agent kẹt: tool không có dữ liệu đó, gọi lại lần nữa cũng vậy.
            # Cắt sớm thay vì đốt nốt trần vòng lặp cho một việc vô ích.
            if _chu_ky(tool, _lam_sach(args)) in set(state.get("da_thu", [])):
                logger.info("Plan lặp lại hành động đã thử, dừng: %s", tool)
                return self._quyet(ANSWER, "Đã tra nhưng không có thêm dữ liệu.")

            return self._quyet(ACT, reason or f"Cần tra thêm bằng {tool}.", tool=tool, args=args)

        return self._quyet(ANSWER, reason or "Đã đủ dữ kiện để trả lời.")

    @staticmethod
    def _quyet(action: str, reason: str, *, tool: str = "", args: dict | None = None) -> dict[str, Any]:
        return {
            "plan_action": action,
            "plan_reason": reason,
            "plan_tool": tool,
            "plan_args": args or {},
        }
