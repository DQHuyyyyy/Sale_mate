"""Tool của agent.

Import các module tool ở đây để decorator @register_tool chạy và tool tự vào
registry. Thêm tool mới = tạo file + thêm một dòng import bên dưới.
"""

from src.agents.tools import (
    inventory,  # noqa: F401 - import để tool tự đăng ký
    search,  # noqa: F401 - import để tool tự đăng ký
    summary,  # noqa: F401 - import để tool tự đăng ký
)
from src.agents.tools.registry import ToolRegistry, register_tool, registry

__all__ = ["ToolRegistry", "register_tool", "registry"]
