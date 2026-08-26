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

from src.agents import chinh_sach
from src.agents.contracts import LLMProvider
from src.agents.graph import CONTEXT_NODES
from src.agents.nguon import loc_nguon_da_dung
from src.agents.nodes.generate import build_messages
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE
from src.agents.nodes.plan import RETRIEVE
from src.agents.state import AgentState, initial_state
from src.agents.suggest import goi_y_bang_model, goi_y_khi_thieu_du_lieu
from src.core.config import Settings
from src.core.exceptions import SalesMateError, UpstreamError
from src.core.logging import get_logger, trace
from src.models.chat import ChatEvent, ChatEventType, ChatRequest, ChatResponse, Citation

logger = get_logger(__name__)


def _ghi_cau_hoi(request: ChatRequest) -> None:
    """Dòng ĐẦU TIÊN của mỗi phiên: người dùng hỏi gì.

    Thiếu nó thì file nhật ký chỉ còn một chuỗi bước không rõ đang giải quyết
    việc gì — xem lại sau vài giờ là vô dụng.

    Câu hỏi là dữ liệu người dùng gõ, nên chỗ này chỉ chấp nhận được vì nhật ký
    nằm ở máy local và đã bị .gitignore chặn. Đừng chuyển thư mục này lên nơi
    dùng chung mà không xem lại quyết định đó.
    """
    logger.info(
        "%s",
        request.message,
        extra={"context": {"buoc": "CÂU HỎI", "so_luot_truoc": len(request.history or [])}},
    )


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
            _ghi_cau_hoi(request)
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
            _ghi_cau_hoi(request)
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

                # Chốt cổng chính sách TRƯỚC khi phát chữ. Trên đường stream đây
                # là ranh giới không quay lại được: token đã gửi đi là khách đã
                # đọc. Cùng hàm `chot()` mà `GenerateNode` gọi — hai đường phải
                # quyết định giống hệt nhau, xem `src/agents/chinh_sach.py`.
                cong = await chinh_sach.chot(state.get("chinh_sach_task"))
                if cong.chan:
                    async for event in self._phat_chan(cong, session_id):
                        yield event
                    return
                if cong.nhay_cam:
                    # Nhãn `nhay_cam` KHÔNG chặn — chỉ gắn cờ rồi cho trả lời
                    # tiếp. Chặn câu "sale hứa giảm 5%" là bỏ mất câu trả lời tốt
                    # hơn hẳn: trợ lý trích đúng tài liệu ưu đãi rồi nói cần sale
                    # xác nhận. Cờ này là thứ `ChatEventType.SENSITIVE` sinh ra
                    # để chở, và tới giờ chưa từng được phát ra.
                    yield ChatEvent(
                        type=ChatEventType.SENSITIVE,
                        content=cong.ly_do,
                        session_id=session_id,
                        data={"nhan": cong.nhan},
                    )

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
                        data={
                            "options": state.get("plan_options", []),
                            # Hỏi ngược thì chưa khẳng định gì — không có gì để
                            # chứng minh, nên không nguồn.
                            "cho_trich_nguon": False,
                        },
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
                    # Không để khách ở ngõ cụt: nhặt lại tiêu chí của lượt trước
                    # rồi trải ra ba phân khu thành nút bấm được.
                    yield ChatEvent(
                        type=ChatEventType.DONE,
                        session_id=session_id,
                        data={
                            "options": goi_y_khi_thieu_du_lieu(state),
                            # Từ chối mà vẫn trưng nguồn là tự phủ định trước
                            # mặt khách — cùng luật với `loc_nguon_da_dung`.
                            "cho_trich_nguon": False,
                        },
                    )
                    return

            # Gom lại chữ đã stream: gợi ý cần ĐỌC ĐƯỢC câu trả lời thì mới bám
            # đúng mạch câu chuyện. Chỉ giữ trong biến cục bộ của một lượt.
            da_tra_loi: list[str] = []
            async for token in self._llm.stream(
                build_messages(state),
                model=self._settings.llm_model_answer,
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
            ):
                da_tra_loi.append(token)
                yield ChatEvent(type=ChatEventType.TOKEN, content=token, session_id=session_id)

            if not da_tra_loi:
                yield ChatEvent(
                    type=ChatEventType.TOKEN,
                    content="Mình chưa tạo được câu trả lời. Bạn thử hỏi lại nhé.",
                    session_id=session_id,
                )

            # Lọc SAU khi có đủ chữ: nguồn phải là thứ câu trả lời thật sự dùng,
            # không phải mọi thứ đã tra. Đây là lý do SOURCES bị giữ lại từ
            # `_prepare_context` rồi mới phát ở đây.
            cau_tra_loi = "".join(da_tra_loi)
            da_dung = loc_nguon_da_dung(
                citations,
                cau_tra_loi,
                co_du_lieu_tool=bool(state.get("tool_context")),
            )
            if da_dung:
                yield ChatEvent(type=ChatEventType.SOURCES, session_id=session_id, citations=da_dung)

            # Gợi ý sinh SAU khi chữ đã chảy hết: khách đang đọc câu trả lời nên
            # không cảm thấy nhịp chờ này. Dùng model rẻ, và mọi lỗi bên trong
            # đều rơi về khuôn tất định. Gắn vào DONE để FE dựng nút khi câu trả
            # lời đã hết chữ.
            yield ChatEvent(
                type=ChatEventType.DONE,
                session_id=session_id,
                data={
                    "options": await goi_y_bang_model(
                        state,
                        self._llm,
                        cau_tra_loi,
                        model=self._settings.llm_model_fast,
                    ),
                    # Backend là nơi DUY NHẤT quyết định lượt này có nguồn hay
                    # không. FE còn một đường sinh nguồn thứ hai — dấu [Mã căn]
                    # model tự viết trong bài — và đường đó không đi qua bộ lọc
                    # nào, nên nó dựng nguồn cả ở lượt vừa bị loại sạch. Xem
                    # `cho_trich_nguon` ở ChatSidebar.jsx.
                    "cho_trich_nguon": bool(da_dung),
                },
            )

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

    async def _phat_chan(self, cong: Any, session_id: str) -> AsyncIterator[ChatEvent]:
        """Phát lời từ chối của cổng chính sách rồi đóng luồng.

        `cho_trich_nguon=False` vì lượt bị chặn không khẳng định gì về căn hộ nào
        — không có gì để trích nguồn.

        Nhưng VẪN có nút gợi ý, và là bộ cố định `GOI_Y_SAU_KHI_CHAN`: người dùng
        vừa bị từ chối là lúc dễ rời đi nhất. Cố định chứ không sinh từ câu hỏi —
        sinh từ câu vừa bị chặn là dựng lối quay lại đúng chủ đề đó.
        """
        yield ChatEvent(
            type=ChatEventType.SENSITIVE,
            content=cong.ly_do,
            session_id=session_id,
            data={"nhan": cong.nhan, "chan": True},
        )
        yield ChatEvent(type=ChatEventType.TOKEN, content=cong.loi_tu_choi, session_id=session_id)
        yield ChatEvent(
            type=ChatEventType.DONE,
            session_id=session_id,
            data={
                "options": list(chinh_sach.GOI_Y_SAU_KHI_CHAN),
                "cho_trich_nguon": False,
            },
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

        if node == "orchestrate":
            # Chỉ báo khi THẬT SỰ leo thang. Node vẫn chạy ở mọi lượt (nó tự gác
            # cổng), nên báo vô điều kiện sẽ hiện một dòng trạng thái vô nghĩa
            # cho cả câu chào hỏi.
            luat = state.get("leo_thang") or ""
            if not luat:
                return []
            return [
                ChatEvent(
                    type=ChatEventType.ROUTE,
                    content=", ".join(state.get("tools_ran", [])) or "đang lập kế hoạch",
                    session_id=session_id,
                    data={
                        "step": "orchestrate",
                        "luat": luat,
                        "tools": list(state.get("tools_ran", [])),
                        "loi": state.get("orchestrator_loi", ""),
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
