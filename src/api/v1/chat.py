"""Endpoint chat của trợ lý AI.

/chat/stream là đường chính — widget dùng SSE để hiện chữ dần.
/chat là đường không stream, giữ cho test và client đơn giản.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from src.api.deps import AgentDep
from src.models.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Hỏi trợ lý (không stream)")
async def chat(request: ChatRequest, agent: AgentDep) -> ChatResponse:
    """Trả về câu trả lời hoàn chỉnh trong một lần."""
    return await agent.answer(request)


@router.post("/stream", summary="Hỏi trợ lý (SSE stream)")
async def chat_stream(request: ChatRequest, agent: AgentDep) -> EventSourceResponse:
    """Stream câu trả lời theo từng token.

    Mỗi message SSE là một ChatEvent dạng JSON:
        {"type": "start"|"route"|"token"|"sources"|"done"|"error", ...}
    """

    async def event_source() -> AsyncIterator[str]:
        async for event in agent.stream(request):
            yield event.to_sse()

    return EventSourceResponse(
        event_source(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx: đừng gom buffer, hỏng streaming
        },
    )
