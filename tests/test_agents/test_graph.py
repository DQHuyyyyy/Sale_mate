"""Test định tuyến và luồng chạy của graph."""

from __future__ import annotations

import pytest

from src.agents.graph import build_graph, build_nodes, route_after_tools
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE
from src.agents.nodes.tools import ToolsNode
from src.agents.state import initial_state
from src.rag.retriever import EmptyRetriever
from tests.conftest import FAKE_REPLY


def test_route_can_tra_cuu_thi_di_retrieve():
    state = initial_state("Chính sách?", "s1")
    state["needs_retrieval"] = True

    assert route_after_tools(state) == "retrieve"


def test_route_khong_can_thi_di_thang_generate():
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = False

    assert route_after_tools(state) == "generate"


def test_route_co_loi_van_di_generate_de_tra_loi_nguoi_dung():
    """Node hỏng thì vẫn phải trả về cái gì đó, không được treo."""
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = True
    state["error"] = "router hỏng"

    assert route_after_tools(state) == "generate"


@pytest.mark.asyncio
async def test_graph_chay_het_luong_va_tra_answer(scripted_llm, settings):
    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)
    graph = build_graph(nodes)

    result = await graph.ainvoke(initial_state("Xin chào", "s1"))

    assert result["answer"] == FAKE_REPLY
    assert result["is_sensitive"] is False


@pytest.mark.asyncio
async def test_graph_tu_choi_khi_can_tai_lieu_ma_khong_co_gi(scripted_llm, settings):
    """EmptyRetriever không trả chunk nào ⇒ guardrail phải chặn."""
    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)
    graph = build_graph(nodes)

    result = await graph.ainvoke(initial_state("Thủ tục sang tên sổ đỏ?", "s1"))

    assert result["answer"] == INSUFFICIENT_MESSAGE


@pytest.mark.asyncio
async def test_graph_hoi_can_cu_the_thi_so_lieu_tu_tool_di_vao_prompt(settings, monkeypatch):
    """Luồng đầu-cuối cho chính ca đã hỏng trên production: hỏi một mã căn.

    Không có tool thì retrieve rỗng ⇒ guardrail từ chối. Có tool thì số liệu
    phải vào context và câu trả lời đi qua được.

    Dùng câu trả lời giả CÓ NHẮC mã căn thay vì `FAKE_REPLY` chung: bộ lọc nguồn
    đối chiếu nhãn nguồn với câu chữ, nên một câu trả lời không khẳng định gì
    ("Xin chào, đây là câu trả lời thử nghiệm") đúng ra phải cho ra 0 nguồn.
    """
    from src.agents.contracts import AgentTool, ToolResult
    from src.agents.state import Intent
    from src.agents.tools.registry import ToolBinding, ToolRegistry
    from src.services.llm import ScriptedProvider

    scripted_llm = ScriptedProvider("Căn VOP345 giá 2,7 tỷ và vẫn còn trống.", delay_s=0)

    class _Ton(AgentTool):
        name = "ton_kho_gia"
        description = "Tra tồn kho."

        async def run(self, **kwargs):
            return ToolResult(
                ok=True, data=[{"unit_code": kwargs["unit_code"], "price_label": "2,7 tỷ"}], source="test:db"
            )

    reg = ToolRegistry()
    reg.add(
        _Ton(),
        ToolBinding(
            intents=frozenset({Intent.LISTING, Intent.PRICE}),
            build_args=lambda q: {"unit_code": "VOP345"} if "VOP345" in q else None,
        ),
    )

    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)
    nodes["tools"] = ToolsNode(reg)
    graph = build_graph(nodes)

    result = await graph.ainvoke(initial_state("Giá căn VOP345 bao nhiêu?", "s1"))

    assert "VOP345" in result["tool_context"]
    assert "2,7 tỷ" in result["tool_context"]
    # Khong bi guardrail chan du EmptyRetriever khong tra chunk nao
    assert result["answer"] != INSUFFICIENT_MESSAGE
    assert [c.kind for c in result["citations"]] == ["db"]
