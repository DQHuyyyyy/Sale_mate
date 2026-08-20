"""Registry cho tool — Registry pattern.

Thêm một tool = tạo một file trong tools/ và gắn @register_tool. Không phải sửa
graph, không phải sửa danh sách ở đâu cả.

Tool khai luôn ĐIỀU KIỆN để agent tự gọi mình, qua `ToolBinding`:

    @register_tool(intents={Intent.LISTING}, build_args=_doc_ma_can)
    class InventoryLookupTool(AgentTool):
        ...

`ToolsNode` đọc bảng này lúc chạy, nên thêm tool mới không đụng tới node lẫn
graph. Tool nào đăng ký trần (`@register_tool` không tham số) thì vẫn nằm trong
registry cho LLM thấy qua `specs()`, nhưng agent không tự gọi — dùng cho tool
chỉ chạy khi có người yêu cầu tường minh.

Hai tầng lọc, cố ý tách rời:

1. `intents` — lọc thô theo nhãn router. Rẻ, không tốn lượt gọi nào.
2. `build_args` — lọc tinh: đọc câu hỏi, trả về tham số hoặc None nếu không rút
   được gì. Trả None nghĩa là "câu này không dành cho tôi", tool không chạy.

Nhờ tầng 2 mà `intents` khai rộng cũng không sao: "tìm căn 2 phòng ngủ" và "căn
VOP345 còn không" cùng nhãn LISTING, nhưng chỉ câu sau rút được mã căn.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from src.agents.contracts import AgentTool
from src.agents.state import Intent
from src.core.logging import get_logger

logger = get_logger(__name__)

# Nhận câu hỏi (+ thực thể đã giải tham chiếu), trả tham số cho tool — hoặc None
# khi không đủ dữ kiện. Tham số thứ hai là TUỲ CHỌN: tool chỉ cần câu hiện tại
# vẫn khai `build_args(query)` như cũ, registry tự thích ứng.
ArgBuilder = Callable[..., dict[str, Any] | None]


def _thich_ung(build_args: ArgBuilder) -> Callable[[str, dict[str, Any]], dict[str, Any] | None]:
    """Bọc builder để gọi được bằng một chữ ký duy nhất.

    Vì sao không bắt cả 6 tool đổi chữ ký cùng lúc: tài liệu dự án hứa "thêm
    tool mới chỉ là thêm một file". Ép mọi builder nhận tham số nó không dùng là
    phá lời hứa đó, và tạo một hàng tham số `_` vô nghĩa trong mỗi file tool.

    Đọc chữ ký MỘT lần lúc đăng ký, không phải mỗi lượt hỏi.
    """
    try:
        nhan_hai_tham_so = len(inspect.signature(build_args).parameters) >= 2
    except (TypeError, ValueError):  # pragma: no cover - builder kỳ lạ
        nhan_hai_tham_so = False

    if nhan_hai_tham_so:
        return lambda query, entities: build_args(query, entities)
    return lambda query, entities: build_args(query)


@dataclass(frozen=True)
class ToolBinding:
    """Điều kiện để agent tự gọi một tool."""

    intents: frozenset[Intent]
    build_args: ArgBuilder

    def dung_args(self, query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Cổng DUY NHẤT để gọi builder — chỗ gọi không cần biết builder nhận mấy tham số."""
        return _thich_ung(self.build_args)(query, entities or {})


class ToolRegistry:
    """Bảng tra tool theo tên, kèm điều kiện tự gọi."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._bindings: dict[str, ToolBinding] = {}

    def add(self, tool: AgentTool, binding: ToolBinding | None = None) -> AgentTool:
        if not tool.name:
            raise ValueError("Tool phải có thuộc tính name")
        if tool.name in self._tools:
            raise ValueError(f"Tool trùng tên: {tool.name}")
        self._tools[tool.name] = tool
        if binding is not None:
            self._bindings[tool.name] = binding
        logger.debug("Đã đăng ký tool %s", tool.name)
        return tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def all(self) -> list[AgentTool]:
        return list(self._tools.values())

    def binding(self, name: str) -> ToolBinding | None:
        return self._bindings.get(name)

    def for_intent(self, intent: Intent | None) -> list[tuple[AgentTool, ToolBinding]]:
        """Các tool khai là phục vụ intent này. Thứ tự theo lúc đăng ký."""
        if intent is None:
            return []
        return [(self._tools[name], binding) for name, binding in self._bindings.items() if intent in binding.intents]

    def specs(self) -> list[dict]:
        """Danh sách schema tool để nạp vào LLM."""
        return [tool.spec() for tool in self._tools.values()]

    def clear(self) -> None:
        self._tools.clear()
        self._bindings.clear()


registry = ToolRegistry()


def register_tool(
    tool_cls: type[AgentTool] | None = None,
    *,
    intents: Iterable[Intent] | None = None,
    build_args: ArgBuilder | None = None,
) -> Any:
    """Decorator đăng ký tool. Dùng được cả hai dạng.

    Đăng ký trần — tool có trong registry nhưng agent không tự gọi:

        @register_tool
        class SomeTool(AgentTool): ...

    Đăng ký kèm điều kiện tự gọi:

        @register_tool(intents={Intent.PRICE}, build_args=_rut_tham_so)
        class SomeTool(AgentTool): ...
    """
    if intents is not None and build_args is None:
        raise ValueError("Khai intents thì phải khai cả build_args, nếu không tool không biết chạy với tham số gì")

    def wrap(cls: type[AgentTool]) -> type[AgentTool]:
        binding = None
        if intents is not None and build_args is not None:
            binding = ToolBinding(intents=frozenset(intents), build_args=build_args)
        registry.add(cls(), binding)
        return cls

    # @register_tool (không ngoặc) -> tool_cls chính là class.
    if tool_cls is not None:
        return wrap(tool_cls)
    # @register_tool(...) -> trả về decorator thật.
    return wrap
