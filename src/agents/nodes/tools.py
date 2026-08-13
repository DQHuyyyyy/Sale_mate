"""Node chạy tool — cầu nối giữa agent và dữ liệu CÓ CẤU TRÚC.

Vì sao cần node này, trong khi đã có RAG: giá và tình trạng căn thay đổi theo
thời gian. Nhét chúng vào vector store nghĩa là trả lời khách bằng một bản chụp
cũ. Tool đọc thẳng nguồn sự thật ngay lúc hỏi.

Node KHÔNG biết tool nào tồn tại. Nó hỏi registry "có tool nào nhận nhãn này
không", rồi để từng tool tự quyết qua `build_args`. Thêm tool mới là thêm một
file trong tools/, không ai phải sửa file này lẫn graph.py.

Node không bao giờ làm đứt luồng: tool trả `ToolResult.failure(...)` chứ không
raise, và tool nào hỏng thì chỉ mình nó bị bỏ qua, các tool khác vẫn chạy.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.contracts import AgentTool, ToolResult
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.logging import get_logger
from src.models.chat import Citation

logger = get_logger(__name__)

_EMPTY: dict[str, Any] = {"tool_context": "", "tool_citations": [], "tools_ran": [], "tool_filters": {}}


def _format(tool: AgentTool, result: ToolResult) -> str:
    """Ghép kết quả thành text cho prompt.

    Dùng JSON thay vì câu văn: model đọc số từ JSON ít sai hơn, và không phải
    bịa thêm chữ nối — hợp với nguyên tắc không bịa số.
    """
    body = json.dumps(result.data, ensure_ascii=False, default=str)
    return f"[{tool.name}] {tool.description}\nKết quả:\n{body}"


class ToolsNode(BaseNode):
    """Chạy các tool khai là phục vụ intent hiện tại."""

    name = "tools"

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        # Cho tiêm registry để test dựng bảng tool riêng, không đụng bảng toàn cục.
        self._registry = registry or default_registry

    async def execute(self, state: AgentState) -> dict[str, Any]:
        candidates = self._registry.for_intent(state.get("intent"))
        if not candidates:
            return _EMPTY

        query = state.get("query", "")
        blocks: list[str] = []
        citations: list[Citation] = []
        ran: list[str] = []
        tieu_chi: dict[str, Any] = {}

        for tool, binding in candidates:
            args = binding.build_args(query)
            if args is None:
                continue

            # Không ghi args vào log: chúng đến từ câu người dùng gõ.
            logger.info("Chạy tool %s", tool.name)
            ran.append(tool.name)
            # Giữ lại tiêu chí đã dùng để tầng trên đồng bộ bộ lọc trên trang
            # tìm kiếm — người dùng hỏi "căn 2-3 tỷ" thì danh sách bên ngoài
            # cũng phải hiện đúng khoảng đó, không để hai bên nói hai kiểu.
            tieu_chi.setdefault(tool.name, args)
            result = await tool.run(**args)

            if not result.ok:
                logger.warning("Tool %s lỗi: %s", tool.name, result.error)
                continue
            if not result.data:
                logger.info("Tool %s không tìm thấy dữ liệu khớp", tool.name)
                continue

            blocks.append(_format(tool, result))
            citations.append(
                Citation(
                    doc_id=result.source or tool.name,
                    title=tool.description.split(".")[0] or tool.name,
                    kind="db",
                )
            )

        if not blocks:
            # Vẫn báo tool nào đã chạy dù không ra dữ liệu — stream cần biết để
            # nói "đã tra nhưng không thấy", khác hẳn với "chưa tra gì".
            return {**_EMPTY, "tools_ran": ran, "tool_filters": tieu_chi}

        # Không trả "metadata" ở đây: BaseNode dùng setdefault để gắn thời gian
        # chạy, trả sẵn khoá đó là nuốt mất số đo của mọi node.
        return {
            "tool_context": "\n\n".join(blocks),
            "tool_citations": citations,
            "tools_ran": ran,
            "tool_filters": tieu_chi,
        }
