"""Facade mà tầng API gọi — API không biết gì về LangGraph.

Hai đường:
- answer(): chạy full graph, trả một lần.
- stream(): chạy dãy node lấy context rồi phát ChatEvent để widget hiện dần.

stream() KHÔNG chạy qua graph vì cần chen event vào giữa các bước. Bù lại, nó
lấy thứ tự node từ `CONTEXT_NODES` trong graph.py để hai đường không lệch nhau —
thêm node mới vào graph là đường stream tự chạy theo.

Event tiến trình đều dùng nhãn ROUTE, chi tiết nằm trong `data.step`, vì
`ChatEventType` là hợp đồng đóng băng.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.graph import CONTEXT_NODES
from src.agents.nodes.generate import build_messages
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE
from src.agents.nodes.plan import RETRIEVE
from src.agents.state import AgentState, initial_state
from src.core.config import Settings
from src.core.exceptions import SalesMateError, UpstreamError
from src.core.logging import get_logger, trace
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

        with trace(session_id=session_id, mode="answer"):
            state = initial_state(request.message, session_id, request.history)
            result = await self._graph.ainvoke(state)

            if result.get("error"):
                logger.error("Agent lỗi: %s", result["error"])
                raise UpstreamError("Trợ lý chưa xử lý được câu hỏi này.")

            logger.info(
                "Trả lời xong",
                extra={
                    "context": {
                        "intent": str(result.get("intent") or ""),
                        "tools_ran": list(result.get("tools_ran", [])),
                        "chunks": len(result.get("chunks") or []),
                        "coverage": round(float(result.get("coverage", 0.0)), 3),
                        "timings_ms": result.get("metadata", {}),
                    }
                },
            )

            return ChatResponse(
                message=result.get("answer", ""),
                session_id=session_id,
                citations=list(result.get("citations", [])),
            )

    # ---------------- Stream ----------------

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """Phát ChatEvent: start → route* → token* → sources → done."""
        session_id = request.session_id or new_session_id()
        with trace(session_id=session_id, mode="stream"):
            async for event in self._stream(request, session_id):
                yield event

    async def _stream(self, request: ChatRequest, session_id: str) -> AsyncIterator[ChatEvent]:
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

                # Agent chủ động hỏi lại: câu hỏi ngược đã có sẵn, phát thẳng.
                # Gọi model để diễn đạt lại chỉ tốn tiền và tạo cơ hội bịa thêm.
                if state.get("plan_action") == "clarify":
                    yield ChatEvent(
                        type=ChatEventType.TOKEN,
                        content=state.get("plan_reason", ""),
                        session_id=session_id,
                    )
                    # Phương án chọn sẵn đi kèm event DONE, trong `data` — khoá
                    # mở rộng tự do, không phải đụng vào hợp đồng ChatEvent.
                    # Gắn vào DONE chứ không phải TOKEN vì FE cần biết câu hỏi
                    # ngược đã hết chữ rồi mới dựng nút bấm.
                    yield ChatEvent(
                        type=ChatEventType.DONE,
                        session_id=session_id,
                        data={"options": state.get("plan_options", [])},
                    )
                    return

                # Có dữ liệu từ tool thì KHÔNG từ chối, dù truy hồi tài liệu
                # rỗng — cùng luật với GuardrailNode._has_enough_context.
                if state.get("needs_retrieval") and not state.get("chunks") and not state.get("tool_context"):
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
        """Chạy dãy node lấy context (không qua graph) rồi phát event tiến trình.

        Dãy node lấy từ `CONTEXT_NODES` trong graph.py, KHÔNG tự liệt kê ở đây.
        Trước kia hàm này gọi tay router rồi retrieve, nên khi thêm node `tools`
        thì đường stream lặng lẽ bỏ qua tool — câu trả lời khi stream tệ hơn khi
        không stream mà không có dấu hiệu gì.
        """
        for name in CONTEXT_NODES:
            node = self._nodes.get(name)
            if node is None:
                continue

            state.update(await node(state))

            for event in self._progress_events(name, state, session_id):
                yield event

        async for event in self._chay_vong_lap(state, session_id):
            yield event

        citations = [*state.get("citations", []), *state.get("tool_citations", [])]
        if citations:
            yield ChatEvent(
                type=ChatEventType.SOURCES,
                session_id=session_id,
                citations=citations,
            )

    async def _chay_vong_lap(self, state: AgentState, session_id: str) -> AsyncIterator[ChatEvent]:
        """Chạy vòng plan ⇄ act, phát ra suy luận từng bước.

        Đường stream không đi qua graph nên phải tự lái vòng lặp, nhưng dùng
        CHÍNH các node object của graph — logic quyết định và trần lần lặp nằm
        trong `PlanNode`, ở đây chỉ là bộ lái. Nhờ vậy stream và graph không thể
        cho ra hành vi khác nhau.

        Không có plan/act trong `nodes` nghĩa là `enable_agent_loop` đang tắt —
        thoát ngay, đường tất định cũ giữ nguyên.
        """
        plan = self._nodes.get("plan")
        act = self._nodes.get("act")
        if plan is None or act is None:
            return

        # Trần thứ hai, phòng khi PlanNode bị sửa hỏng: bộ lái này không được
        # quay vòng vô hạn dù kế hoạch có nói gì.
        for _ in range(self._settings.agent_max_iterations + 1):
            state.update(await plan(state))

            ly_do = state.get("plan_reason", "")
            if ly_do:
                yield ChatEvent(
                    type=ChatEventType.ROUTE,
                    content=ly_do,
                    session_id=session_id,
                    data={"step": "plan", "action": state.get("plan_action", "")},
                )

            # Plan đòi tra tài liệu trước khi kết luận. Chạy chính node retrieve
            # của graph rồi quay lại plan — cùng một node object, nên stream và
            # graph không thể lệch hành vi.
            if state.get("plan_action") == RETRIEVE:
                retrieve = self._nodes.get("retrieve")
                if retrieve is None:
                    return
                state.update(await retrieve(state))
                yield ChatEvent(
                    type=ChatEventType.ROUTE,
                    session_id=session_id,
                    data={"step": "retrieve", "found": len(state.get("chunks", []))},
                )
                continue

            if state.get("plan_action") != "act":
                return

            state.update(await act(state))
            yield ChatEvent(
                type=ChatEventType.ROUTE,
                content=state.get("plan_tool", ""),
                session_id=session_id,
                data={
                    "step": "act",
                    "tool": state.get("plan_tool", ""),
                    "iteration": int(state.get("iterations", 0)),
                },
            )

    def _progress_events(self, node: str, state: AgentState, session_id: str) -> list[ChatEvent]:
        """Mô tả việc vừa làm để FE hiện dòng trạng thái.

        Dùng ROUTE cho mọi bước vì `ChatEventType` là hợp đồng ĐÓNG BĂNG, không
        được thêm nhãn mới trong PR tính năng. Chi tiết đi trong `data` — trường
        này vốn là dict tự do, FE đọc `data.step` để biết đang ở bước nào.
        """
        if node == "router":
            intent = state.get("intent")
            if intent is None:
                return []
            return [
                ChatEvent(
                    type=ChatEventType.ROUTE,
                    content=intent.value,
                    session_id=session_id,
                    data={
                        "step": "router",
                        "needs_retrieval": bool(state.get("needs_retrieval")),
                    },
                )
            ]

        if node == "tools":
            ran = list(state.get("tools_ran", []))
            if not ran:
                return []
            return [
                ChatEvent(
                    type=ChatEventType.ROUTE,
                    content=", ".join(ran),
                    session_id=session_id,
                    data={
                        "step": "tools",
                        "tools": ran,
                        # Phân biệt "đã tra nhưng không thấy" với "chưa tra gì".
                        "found": bool(state.get("tool_context")),
                        # Tiêu chí đã lọc, để giao diện đồng bộ danh sách bên
                        # ngoài với câu trả lời trong chat.
                        "filters": state.get("tool_filters", {}),
                    },
                )
            ]

        if node == "retrieve":
            chunks = state.get("chunks") or []
            if not chunks:
                return []
            return [
                ChatEvent(
                    type=ChatEventType.ROUTE,
                    content=f"{len(chunks)} đoạn tài liệu",
                    session_id=session_id,
                    data={
                        "step": "retrieve",
                        "chunks": len(chunks),
                        "coverage": round(float(state.get("coverage", 0.0)), 3),
                    },
                )
            ]

        return []


def new_session_id() -> str:
    return uuid.uuid4().hex
