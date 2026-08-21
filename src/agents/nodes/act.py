"""Node thực thi — chạy tool mà node plan đã chọn.

Tách khỏi `ToolsNode`: `ToolsNode` chạy tool theo LUẬT (nhãn router + build_args),
node này chạy tool theo QUYẾT ĐỊNH CỦA MODEL với tham số model tự đặt. Hai đường
vào khác nhau nên rủi ro cũng khác — tham số ở đây do model sinh ra, phải để
chính tool validate qua `args_schema` chứ không tin sẵn.

Bằng chứng CỘNG DỒN chứ không ghi đè: vòng lặp có thể gọi nhiều tool, mỗi lần
thêm một mảnh, và node plan nhìn toàn bộ để quyết bước sau.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.nodes.base import BaseNode

# Dùng lại `_format` và `_nguon_cua_tool` của ToolsNode thay vì giữ bản chép thứ
# hai: cả hai đường đều dựng ngữ cảnh và nguồn cho CÙNG một câu trả lời, lệch
# nhau là cùng một câu hỏi cho ra hai kiểu kết quả tuỳ vào việc đi đường tất
# định hay đường vòng lặp. Bản chép ở đây từng giữ `[{tool.name}]` sau khi bản
# kia đã bỏ ngoặc vuông, và từng lấy câu đầu trong description làm nhãn nguồn.
from src.agents.nodes.tools import _format, _nguon_cua_tool
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.logging import get_logger

logger = get_logger(__name__)


def _lam_sach(args: dict[str, Any]) -> dict[str, Any]:
    """Bỏ tham số rỗng do model sinh ra.

    Model có xu hướng điền ĐỦ mọi trường trong schema, dùng "" cho thứ không áp
    dụng: {"unit_code": "VOP397", "building": "", "unit_type": ""}. Tool lại chỉ
    coi None là "không lọc", nên "" thành bộ lọc `ILIKE ''` và không khớp gì —
    tra đúng mã căn vẫn trả rỗng, agent tưởng thiếu dữ liệu rồi lặp lại y hệt
    cho tới hết trần.

    Đây là biên duy nhất tham số do model sinh đi vào hệ thống, nên làm sạch ở
    đây thay vì sửa từng tool.
    """
    return {k: v for k, v in args.items() if v not in (None, "", [], {})}


def _chu_ky(tool: str, args: dict[str, Any]) -> str:
    """Dấu vân tay của một hành động, để nhận ra agent đang lặp lại chính nó."""
    return f"{tool}({json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)})"


class ActNode(BaseNode):
    """Chạy đúng một tool theo kế hoạch, cộng kết quả vào bằng chứng."""

    name = "act"

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or default_registry

    async def execute(self, state: AgentState) -> dict[str, Any]:
        # Luôn tăng số vòng, kể cả khi tool hỏng. Nếu chỉ tăng lúc thành công thì
        # một tool luôn lỗi sẽ khiến agent lặp tới trần thời gian chứ không phải
        # trần vòng lặp.
        buoc_moi = int(state.get("iterations", 0)) + 1
        ket_qua: dict[str, Any] = {"iterations": buoc_moi}

        ten = state.get("plan_tool", "")
        tool = self._registry.get(ten)
        if tool is None:
            logger.warning("Không có tool %r để chạy", ten)
            return ket_qua

        args = _lam_sach(state.get("plan_args") or {})
        ket_qua["da_thu"] = [*state.get("da_thu", []), _chu_ky(ten, args)]

        logger.info("Agent gọi tool %s (vòng %s)", ten, buoc_moi)
        result = await tool.run(**args)

        ket_qua["tools_ran"] = [*state.get("tools_ran", []), ten]

        if not result.ok:
            logger.warning("Tool %s lỗi: %s", ten, result.error)
            return ket_qua
        if not result.data:
            logger.info("Tool %s không tìm thấy dữ liệu khớp", ten)
            return ket_qua

        cu = state.get("tool_context", "")
        moi = _format(tool, result)
        ket_qua["tool_context"] = f"{cu}\n\n{moi}" if cu else moi
        ket_qua["tool_citations"] = [*state.get("tool_citations", []), *_nguon_cua_tool(tool, result)]
        return ket_qua
