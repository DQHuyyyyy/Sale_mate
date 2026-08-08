"""Test định tuyến và luồng chạy của graph."""

from __future__ import annotations

import pytest

from src.agents.graph import build_graph, build_nodes, route_after_router
from src.agents.state import initial_state
from src.rag.retriever import EmptyRetriever
from tests.conftest import FAKE_REPLY


def test_route_can_tra_cuu_thi_di_retrieve():
    state = initial_state("Chính sách?", "s1")
    state["needs_retrieval"] = True

    assert route_after_router(state) == "retrieve"


def test_route_khong_can_thi_di_thang_generate():
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = False

    assert route_after_router(state) == "generate"


def test_route_co_loi_van_di_generate_de_tra_loi_nguoi_dung():
    """Node hỏng thì vẫn phải trả về cái gì đó, không được treo."""
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = True
    state["error"] = "router hỏng"

    assert route_after_router(state) == "generate"


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

    assert "chưa có đủ dữ liệu" in result["answer"].lower()
