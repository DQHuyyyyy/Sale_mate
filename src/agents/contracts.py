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


# ---------------------------------------------------------------------------
# Tool calling — cổng ra LLM cho orchestrator
#
# Vì sao THÊM chứ không sửa `LLMProvider`: hợp đồng đó đang có 4 chỗ gọi và
# `complete()` trả về `str` trần, không chở nổi tool call lẫn số token. Nhét
# thêm vào là sửa chữ ký của thứ đang chạy thật. Thêm một Protocol thứ hai thì
# code cũ không phải đổi một ký tự, và provider nào chỉ biết sinh chữ vẫn hợp lệ.
#
# Transcript của orchestrator KHÔNG dùng `models/chat.py`: đó là hợp đồng với
# frontend, còn mấy lượt gọi tool này là chuyện nội bộ tầng agent, không bao giờ
# ra tới widget. Trộn hai thứ là buộc FE phải biết về tool call.
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """Một lần model xin gọi tool."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallOutput(BaseModel):
    """Kết quả trả ngược lại cho model sau khi đã chạy tool.

    Khác `ToolResult` ở trên: `ToolResult` là thứ tool trả cho hệ thống (có
    `data` kiểu tự do, có `source` để trích dẫn), còn cái này là thứ đã ghép
    thành chữ để nhét lại vào hội thoại. Một cái hướng vào trong, một cái
    hướng ra ngoài model.
    """

    call_id: str
    content: str
    is_error: bool = False


class OrchestratorMessage(BaseModel):
    """Một lượt trong hội thoại nội bộ giữa orchestrator và model."""

    role: str  # "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_outputs: list[ToolCallOutput] = Field(default_factory=list)


class LLMTurn(BaseModel):
    """Kết quả một lượt gọi model có tool.

    Chở luôn số token: bộ đếm ngân sách cần nó, và đây là hợp đồng viết mới nên
    không phải chịu cái thiếu của `LLMProvider.complete()` — chỗ đó trả `str`
    trần nên chi phí phải dò bằng `getattr` vào chi tiết cài đặt.
    """

    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str = ""
    token_vao: int = 0
    token_ra: int = 0
    token_doc_cache: int = 0
    # Ghi cache tính 1,25× giá vào. Không đếm là bộ phanh ngân sách báo
    # THIẾU, và nó nhả phanh muộn hơn mức đã cấu hình.
    token_ghi_cache: int = 0

    @property
    def con_goi_tool(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class ToolCallingProvider(Protocol):
    """Cổng ra LLM có tool calling gốc. OpenAI và Anthropic cùng cài.

    `system` tách khỏi `history` vì hai lẽ: Anthropic nhận system như tham số
    riêng chứ không phải một message, và đó là phần đầu ỔN ĐỊNH của prompt —
    tách ra mới đặt được mốc cache lên đúng chỗ.
    """

    async def run_turn(
        self,
        system: str,
        history: list[OrchestratorMessage],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMTurn: ...
