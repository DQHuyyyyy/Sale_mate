"""Node khởi động cổng phân loại chính sách. KHÔNG chờ kết quả.

Nó là node ĐẦU TIÊN của dãy, và việc duy nhất nó làm là bắn một task chạy nền rồi
trả về ngay — thời gian chạy của node này luôn ~0ms. Kết quả được `chot()` lấy
ngay trước `generate`, tức sau khi `tools` và `retrieve` đã chạy xong.

Vì sao tách khởi động ra khỏi chờ đợi thay vì làm một node bình thường: node bình
thường chạy nối tiếp, và một lượt gọi Sonnet 5 nối tiếp trên đường đi chung là
đúng thứ đã làm `CHE_DO_LEO_THANG=moi_luot` cộng 4,3s vào mọi câu hỏi. Ở đây lượt
phân loại chạy cùng lúc với truy hồi nên phần lớn thời gian của nó bị che khuất.

Xem `src/agents/chinh_sach.py` cho phần quyết định.
"""

from __future__ import annotations

from typing import Any

from src.agents import chinh_sach
from src.agents.contracts import ToolCallingProvider
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.models.chat import MessageRole


def _cau_user_gan_nhat(state: AgentState) -> str:
    """Câu NGƯỜI DÙNG hỏi ở lượt trước, để bắt lượt bám đuôi.

    Lấy lượt user chứ không lấy lượt assistant: câu trả lời của trợ lý dài và đầy
    từ khoá bất động sản, nhét vào sẽ kéo mọi thứ về `binh_thuong`.
    """
    for m in reversed(state.get("history") or []):
        if m.role == MessageRole.USER:
            return m.content
    return ""


class ChinhSachNode(BaseNode):
    """Bắn lượt phân loại chạy nền, trả về ngay."""

    name = "chinh_sach"

    def __init__(self, provider: ToolCallingProvider | None, *, model: str) -> None:
        self._provider = provider
        self._model = model

    async def execute(self, state: AgentState) -> dict[str, Any]:
        task = chinh_sach.khoi_dong(
            self._provider,
            state.get("query", ""),
            self._model,
            _cau_user_gan_nhat(state),
        )
        return {"chinh_sach_task": task}

    def tom_tat(self, result: dict[str, Any]) -> str:
        return "đã bắn lượt phân loại" if result.get("chinh_sach_task") else "bỏ qua (câu xã giao)"
