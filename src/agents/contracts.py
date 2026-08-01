"""HỢP ĐỒNG của module AI_core.

Module khác (api) chỉ import từ file này. Bên trong agents/ dùng gì là việc
của AI_core, đổi LangGraph sang thứ khác cũng không lộ ra ngoài.

Chủ sở hữu: viet (src/agents/**)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.models.chat import ChatEvent, ChatMessage, ChatRequest, ChatResponse


class ToolResult(BaseModel):
    """Kết quả một lần gọi tool.

    Tool KHÔNG raise ra ngoài — lỗi được gói vào đây để agent tự quyết định
    xử lý tiếp thế nào thay vì làm đứt cả luồng.
    """

    ok: bool = True
    data: Any = None
    error: str = ""
    source: str = Field(default="", description="Nguồn dữ liệu, dùng để trích dẫn")

    @classmethod
    def failure(cls, message: str) -> ToolResult:
        return cls(ok=False, error=message)


class AgentTool(ABC):
    """Lớp cơ sở cho mọi tool.

    Tool là cách agent lấy dữ liệu ĐỘNG (tồn kho, giá) — thứ không được đưa
    vào vector store vì RAG luôn là bản chụp cũ.
    """

    name: str = ""
    description: str = ""
    args_schema: type[BaseModel] | None = None

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Thực thi tool. Không raise — trả ToolResult.failure() khi lỗi."""

    def spec(self) -> dict[str, Any]:
        """Mô tả tool theo dạng JSON schema để nạp vào LLM."""
        parameters: dict[str, Any] = {"type": "object", "properties": {}}
        if self.args_schema is not None:
            parameters = self.args_schema.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


@runtime_checkable
class LLMProvider(Protocol):
    """Cổng ra LLM. Adapter pattern — đổi OpenAI ↔ Claude ↔ Gemini tại bootstrap."""

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class AgentService(Protocol):
    """Mặt tiền mà tầng API gọi. API không biết gì về LangGraph."""

    async def answer(self, request: ChatRequest) -> ChatResponse: ...

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]: ...
