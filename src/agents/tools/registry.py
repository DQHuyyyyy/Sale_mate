"""Registry cho tool — Registry pattern.

Thêm một tool = tạo một file trong tools/ và gắn @register_tool. Không phải sửa
graph, không phải sửa danh sách ở đâu cả.
"""

from __future__ import annotations

from src.agents.contracts import AgentTool
from src.core.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Bảng tra tool theo tên."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def add(self, tool: AgentTool) -> AgentTool:
        if not tool.name:
            raise ValueError("Tool phải có thuộc tính name")
        if tool.name in self._tools:
            raise ValueError(f"Tool trùng tên: {tool.name}")
        self._tools[tool.name] = tool
        logger.debug("Đã đăng ký tool %s", tool.name)
        return tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def all(self) -> list[AgentTool]:
        return list(self._tools.values())

    def specs(self) -> list[dict]:
        """Danh sách schema tool để nạp vào LLM."""
        return [tool.spec() for tool in self._tools.values()]

    def clear(self) -> None:
        self._tools.clear()


registry = ToolRegistry()


def register_tool(tool_cls: type[AgentTool]) -> type[AgentTool]:
    """Decorator đăng ký tool.

    Dùng:
        @register_tool
        class InventoryLookupTool(AgentTool):
            name = "inventory_lookup"
            ...
    """
    registry.add(tool_cls())
    return tool_cls
