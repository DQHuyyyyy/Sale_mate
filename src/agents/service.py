"""Facade mà tầng API gọi — API không biết gì về LangGraph.

Hai đường:
- answer(): chạy full graph (router → retrieve → generate → guardrail), không stream.
- stream(): phát ChatEvent để widget hiển thị dần.

GIAI ĐOẠN HIỆN TẠI enable_rag=False: stream() đi thẳng LLM, chưa tra tài liệu —
đúng phạm vi đã chốt. Khi module Data có dữ liệu thật, bật enable_rag=True thì
stream() chạy router + retrieve trước rồi mới sinh chữ, và phát thêm event
`route` + `sources`. FE không phải đổi gì vì hợp đồng ChatEvent đã có sẵn chỗ.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.generate import build_messages
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE
from src.agents.state import AgentState, initial_state
from src.core.config import Settings
from src.core.exceptions import SalesMateError, UpstreamError
from src.core.logging import get_logger
from src.models.chat import ChatEvent, ChatEventType, ChatRequest, ChatResponse, Citation

logger = get_logger(__name__)


class LangGraphAgentService:
    """Cài đặt AgentService trên LangGraph."""

    def __init__(
        self,
        graph: Any,
        llm: LLMProvider,
        settings: Settings,
        *,
        nodes: dict[str, Any] | None = None,
        enable_rag: bool = False,
    ) -> None:
        self._graph = graph
        self._llm = llm
        self._settings = settings
        self._nodes = nodes or {}
        self._enable_rag = enable_rag

    # ---------------- Không stream ----------------

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """Chạy toàn bộ graph, trả về một lần."""
        session_id = request.session_id or new_session_id()
        state = initial_state(request.message, session_id, request.history)

        result = await self._graph.ainvoke(state)

        if result.get("error"):
            logger.error("Agent lỗi: %s", result["error"])
            raise UpstreamError("Trợ lý chưa xử lý được câu hỏi này.")

        return ChatResponse(
            message=result.get("answer", ""),
            session_id=session_id,
            citations=list(result.get("citations", [])),
        )

    # ---------------- Stream ----------------

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """Phát ChatEvent: start → [route] → token* → [sources] → done."""
        session_id = request.session_id or new_session_id()
        yield ChatEvent(type=ChatEventType.START, session_id=session_id)

        state = initial_state(request.message, session_id, request.history)
        citations: list[Citation] = []

        try:
            if self._enable_rag:
                async for event in self._prepare_context(state, session_id):
                    if event.type == ChatEventType.SOURCES:
                        citations = event.citations
                    else:
                        yield event

                if state.get("needs_retrieval") and not state.get("chunks"):
                    yield ChatEvent(
                        type=ChatEventType.TOKEN,
                        content=INSUFFICIENT_MESSAGE,
                        session_id=session_id,
                    )
                    yield ChatEvent(type=ChatEventType.DONE, session_id=session_id)
                    return

            produced = False
            async for token in self._llm.stream(
                build_messages(state),
                model=self._settings.llm_model_answer,
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
            ):
                produced = True
                yield ChatEvent(type=ChatEventType.TOKEN, content=token, session_id=session_id)

            if not produced:
                yield ChatEvent(
                    type=ChatEventType.TOKEN,
                    content="Mình chưa tạo được câu trả lời. Bạn thử hỏi lại nhé.",
                    session_id=session_id,
                )

            if citations:
                yield ChatEvent(type=ChatEventType.SOURCES, session_id=session_id, citations=citations)

            yield ChatEvent(type=ChatEventType.DONE, session_id=session_id)

        except SalesMateError as exc:
            logger.warning("Stream dừng do lỗi nghiệp vụ: %s", exc.code)
            yield ChatEvent(type=ChatEventType.ERROR, content=exc.message, session_id=session_id)
        except Exception:  # noqa: BLE001 - biên ngoài cùng của stream
            logger.exception("Stream lỗi ngoài dự kiến")
            yield ChatEvent(
                type=ChatEventType.ERROR,
                content="Trợ lý đang gặp sự cố. Bạn thử lại sau ít phút nhé.",
                session_id=session_id,
            )

    async def _prepare_context(self, state: AgentState, session_id: str) -> AsyncIterator[ChatEvent]:
        """Chạy router + retrieve trực tiếp (không qua graph) để lấy context.

        Sửa state tại chỗ rồi phát event route/sources cho FE hiển thị.
        """
        router = self._nodes.get("router")
        retrieve = self._nodes.get("retrieve")
        if router is None or retrieve is None:
            return

        state.update(await router(state))
        intent = state.get("intent")
        if intent is not None:
            yield ChatEvent(
                type=ChatEventType.ROUTE,
                content=intent.value,
                session_id=session_id,
                data={"needs_retrieval": bool(state.get("needs_retrieval"))},
            )

        state.update(await retrieve(state))
        if state.get("citations"):
            yield ChatEvent(
                type=ChatEventType.SOURCES,
                session_id=session_id,
                citations=list(state["citations"]),
            )


def new_session_id() -> str:
    return uuid.uuid4().hex
