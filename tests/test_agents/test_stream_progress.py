"""Test luồng stream: event tiến trình và đồng bộ với graph.

Trọng tâm là chống hồi quy cho một lỗi đã xảy ra thật: `_prepare_context` từng
tự liệt kê router+retrieve, nên khi thêm node `tools` thì đường stream lặng lẽ
bỏ qua tool — trả lời khi stream tệ hơn khi không stream mà không báo gì.
"""

from __future__ import annotations

import pytest

from src.agents.graph import CONTEXT_NODES, build_graph, build_nodes
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE
from src.agents.service import LangGraphAgentService
from src.agents.state import Intent
from src.core.logging import trace, trace_context
from src.models.chat import ChatEventType, ChatRequest, Citation
from src.rag.retriever import EmptyRetriever
from src.services.llm import ScriptedProvider, ScriptedToolCallingProvider


def _service(scripted_llm, settings, *, retriever=None, tools_node=None):
    nodes = build_nodes(scripted_llm, retriever or EmptyRetriever(), settings)
    if tools_node is not None:
        nodes["tools"] = tools_node
    return LangGraphAgentService(build_graph(nodes), scripted_llm, settings, nodes=nodes, enable_rag=True)


async def _collect(service, message):
    return [event async for event in service.stream(ChatRequest(message=message))]


# ---------- Đồng bộ giữa graph và stream ----------


def test_context_nodes_khop_voi_node_dung_trong_graph(scripted_llm, settings):
    """Mọi node trong CONTEXT_NODES phải tồn tại — sai tên là stream bỏ qua âm thầm.

    Dựng bản ĐẦY ĐỦ (bật mọi cờ) vì `orchestrate` là node tuỳ chọn: nó chỉ có
    khi `enable_orchestrator` bật. Kiểm trên bản tối thiểu thì node tuỳ chọn
    nào cũng làm test đỏ, còn kiểm trên bản đầy đủ thì vẫn bắt được lỗi thật —
    gõ sai tên node trong CONTEXT_NODES.
    """
    day_du = settings.model_copy(update={"enable_orchestrator": True})
    nodes = build_nodes(scripted_llm, EmptyRetriever(), day_du, ScriptedToolCallingProvider())

    assert set(CONTEXT_NODES) <= set(nodes)


def test_node_tuy_chon_tat_co_thi_stream_van_chay(scripted_llm, settings):
    """Tắt cờ thì `orchestrate` không tồn tại, và đường stream phải bỏ qua nó."""
    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)

    assert "orchestrate" not in nodes
    assert set(CONTEXT_NODES) - set(nodes) == {"orchestrate"}


def test_tools_nam_trong_duong_lay_context():
    """Chốt chặn hồi quy: quên tools ở đây là stream mất hết tool."""
    assert "tools" in CONTEXT_NODES


# ---------- Event tiến trình ----------


@pytest.mark.asyncio
async def test_phat_event_router_kem_step(scripted_llm, settings):
    events = await _collect(_service(scripted_llm, settings), "Xin chào")

    routes = [e for e in events if e.type == ChatEventType.ROUTE]
    assert any(e.data.get("step") == "router" for e in routes)


@pytest.mark.asyncio
async def test_phat_event_tool_khi_tool_chay(scripted_llm, settings):
    class _Tools:
        async def __call__(self, state):  # noqa: ARG002
            return {
                "tool_context": '{"unit_code": "VOP345"}',
                "tool_citations": [],
                "tools_ran": ["inventory_lookup"],
            }

    events = await _collect(_service(scripted_llm, settings, tools_node=_Tools()), "giá căn VOP345")

    tool_events = [e for e in events if e.data.get("step") == "tools"]
    assert len(tool_events) == 1
    assert tool_events[0].data["tools"] == ["inventory_lookup"]
    assert tool_events[0].data["found"] is True


@pytest.mark.asyncio
async def test_phan_biet_da_tra_nhung_khong_thay_voi_chua_tra(scripted_llm, settings):
    class _Rong:
        async def __call__(self, state):  # noqa: ARG002
            return {"tool_context": "", "tool_citations": [], "tools_ran": ["inventory_search"]}

    events = await _collect(_service(scripted_llm, settings, tools_node=_Rong()), "tìm căn 2PN")

    tool_events = [e for e in events if e.data.get("step") == "tools"]
    assert tool_events[0].data["found"] is False


@pytest.mark.asyncio
async def test_khong_phat_event_tool_khi_khong_tool_nao_chay(scripted_llm, settings):
    events = await _collect(_service(scripted_llm, settings), "Xin chào")

    assert not [e for e in events if e.data.get("step") == "tools"]


# ---------- Không từ chối khi tool đã có dữ liệu ----------


@pytest.mark.asyncio
async def test_co_du_lieu_tool_thi_van_tra_loi_du_truy_hoi_rong(scripted_llm, settings):
    """Cùng luật với GuardrailNode: tool có số liệu thì không được từ chối."""

    class _Tools:
        async def __call__(self, state):  # noqa: ARG002
            return {
                "tool_context": '{"unit_code": "VOP345", "price_label": "2,7 tỷ"}',
                "tool_citations": [],
                "tools_ran": ["inventory_lookup"],
            }

    events = await _collect(_service(scripted_llm, settings, tools_node=_Tools()), "giá căn VOP345 bao nhiêu")

    noi_dung = "".join(e.content for e in events if e.type == ChatEventType.TOKEN)
    assert INSUFFICIENT_MESSAGE not in noi_dung


@pytest.mark.asyncio
async def test_khong_co_gi_ca_thi_van_tu_choi(scripted_llm, settings):
    events = await _collect(_service(scripted_llm, settings), "Thủ tục sang tên sổ đỏ?")

    noi_dung = "".join(e.content for e in events if e.type == ChatEventType.TOKEN)
    assert INSUFFICIENT_MESSAGE in noi_dung


# ---------- Tracing ----------


def test_trace_gan_truong_vao_context_va_tra_lai_sau_khi_thoat():
    assert trace_context.get() == {}

    with trace(session_id="abc"):
        assert trace_context.get()["session_id"] == "abc"
        with trace(mode="stream"):
            assert trace_context.get() == {"session_id": "abc", "mode": "stream"}

    assert trace_context.get() == {}


@pytest.mark.asyncio
async def test_stream_dat_session_id_vao_trace(scripted_llm, settings):
    thay: list[dict] = []

    class _Bat:
        async def __call__(self, state):  # noqa: ARG002
            thay.append(dict(trace_context.get()))
            return {"intent": Intent.GENERAL, "needs_retrieval": False}

    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)
    nodes["router"] = _Bat()
    service = LangGraphAgentService(build_graph(nodes), scripted_llm, settings, nodes=nodes, enable_rag=True)

    await _collect(service, "Xin chào")

    assert thay and thay[0]["mode"] == "stream"
    assert thay[0]["session_id"]


# ---------- Gợi ý câu hỏi tiếp theo ----------


@pytest.mark.asyncio
async def test_done_mang_goi_y_tren_duong_tra_loi_thuong(scripted_llm, settings):
    """Widget dựng nút từ `data.options` của DONE — thiếu khoá này là mất tính năng."""

    class _Tools:
        name = "tools"

        async def __call__(self, state):
            return {
                "tool_context": '[inventory_search] x\nKết quả:\n[{"unit_code": "VOP758", '
                '"subdivision": "Ocean Park 1"}, {"unit_code": "VOP285", "subdivision": "Ocean Park 1"}]',
                "tool_citations": [],
                "tools_ran": ["inventory_search"],
                "tool_filters": {"inventory_search": {"subdivision": "Ocean Park 1"}},
            }

    events = await _collect(_service(scripted_llm, settings, tools_node=_Tools()), "căn ở Ocean Park 1")

    done = [e for e in events if e.type == ChatEventType.DONE]
    assert len(done) == 1
    goi_y = done[0].data.get("options")
    assert goi_y and all(isinstance(c, str) and c for c in goi_y)
    assert any("VOP758" in c for c in goi_y)


@pytest.mark.asyncio
async def test_thieu_du_lieu_van_co_loi_ra_thay_vi_ngo_cut(scripted_llm, settings):
    """Ca thật trong ảnh: câu hỏi cụt lủn không được kết thúc bằng một lời từ chối trơ."""
    events = await _collect(_service(scripted_llm, settings), "Thủ tục sang tên sổ đỏ?")

    done = [e for e in events if e.type == ChatEventType.DONE]
    goi_y = done[0].data.get("options")
    assert len(goi_y) == 3
    assert all("Ocean Park" in c for c in goi_y)


# ---------- Cờ chặn FE tự dựng nguồn ----------


@pytest.mark.asyncio
async def test_thieu_du_lieu_thi_cam_trich_nguon(scripted_llm, settings):
    """Ca thật: trợ lý hỏi ngược "bạn muốn lọc theo tiêu chí nào?" mà dưới đó
    vẫn có Nguồn: VOP758, VOP247, VOP619.

    Backend đã lọc sạch nguồn rồi, nhưng FE còn một đường sinh nguồn THỨ HAI —
    dấu `[Mã căn]` model tự viết trong bài — và đường đó không đi qua bộ lọc
    nào. Nên backend phải nói thẳng ra là lượt này cấm trích.
    """
    events = await _collect(_service(scripted_llm, settings), "Thủ tục sang tên sổ đỏ?")

    done = [e for e in events if e.type == ChatEventType.DONE]

    assert done[0].data.get("cho_trich_nguon") is False


@pytest.mark.asyncio
async def test_luot_co_nguon_that_thi_van_cho_trich(scripted_llm, settings):
    """Chốt ngược: cờ này không được tắt nguồn của lượt trả lời đàng hoàng."""

    class _Tools:
        name = "tools"

        async def __call__(self, state):
            return {
                "tool_context": '[inventory_lookup] x\nKết quả:\n[{"unit_code": "VOP758"}]',
                "tool_citations": [Citation(doc_id="inventory:postgres", title="VOP758", kind="db")],
                "tools_ran": ["inventory_lookup"],
                "tool_filters": {"inventory_lookup": {"unit_code": "VOP758"}},
            }

    svc = _service(scripted_llm, settings, tools_node=_Tools())
    svc._llm = ScriptedProvider("Căn VOP758 giá 2,750 tỷ đồng.", delay_s=0)

    events = await _collect(svc, "Căn VOP758 giá bao nhiêu?")

    done = [e for e in events if e.type == ChatEventType.DONE]
    nguon = [e for e in events if e.type == ChatEventType.SOURCES]

    assert done[0].data.get("cho_trich_nguon") is True
    assert [c.title for c in nguon[0].citations] == ["VOP758"]
