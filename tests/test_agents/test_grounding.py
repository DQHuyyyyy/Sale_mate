"""Test chống Hallucination, Ép Grounding và Định dạng Trích dẫn Nguồn."""

from __future__ import annotations

import pytest

from src.agents.graph import build_graph, build_nodes
from src.agents.nodes.generate import GenerateNode, build_messages
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE, GuardrailNode
from src.agents.prompts import system_prompt
from src.agents.state import initial_state
from src.data.contracts import Chunk, RetrievalResult
from src.data.retrieval.retriever import DefaultRetriever, EmptyRetriever
from tests.conftest import FAKE_REPLY


@pytest.mark.asyncio
async def test_guardrail_chong_hallucination_khi_khong_co_du_lieu():
    """Hỏi câu không có trong dữ liệu (VOP9999) -> Guardrail chặn và từ chối, không suy đoán."""
    state = initial_state("Căn VOP9999 giá bao nhiêu tiền?", "session_1")
    state["needs_retrieval"] = True
    state["chunks"] = []
    state["coverage"] = 0.0

    guardrail = GuardrailNode(coverage_threshold=0.35)
    result = await guardrail(state)

    assert result["answer"] == INSUFFICIENT_MESSAGE
    assert result["citations"] == []
    assert result["is_sensitive"] is False


@pytest.mark.asyncio
async def test_build_messages_ep_grounding_va_dinh_dang_trich_dan():
    """Kiểm tra build_messages đưa đúng chỉ thị Grounding & bắt buộc trích dẫn [Mã căn] vào prompt."""
    state = initial_state("Căn VOP398 giá bao nhiêu?", "session_1")
    state["context"] = "Ma can: VOP398, Gia: 3.1 tỷ, Toa: R103."

    messages = build_messages(state)
    user_prompt = messages[-1].content

    assert "<ngu_canh>" in user_prompt
    assert "Ma can: VOP398, Gia: 3.1 tỷ" in user_prompt
    assert "trích dẫn nguồn bằng định dạng [Mã căn] hoặc [Tên tài liệu]" in user_prompt.lower() or "trích dẫn" in user_prompt.lower()


@pytest.mark.asyncio
async def test_system_prompt_co_dinh_dang_trich_dan():
    """System prompt chứa nguyên tắc bắt buộc trích dẫn nguồn [Mã căn] / [Tên tài liệu]."""
    prompt = system_prompt()

    assert "Chỉ dựa vào ngữ cảnh được cấp" in prompt
    assert "Chống Hallucination" in prompt or "bịa" in prompt
    assert "[Mã căn]" in prompt
    assert "[Tên tài liệu]" in prompt


@pytest.mark.asyncio
async def test_graph_grounding_end_to_end_tu_choi_khi_retrieval_rong(scripted_llm, settings):
    """E2E Graph: Hỏi thông tin dự án chưa có dữ liệu -> Agent từ chối bằng thông điệp mẫu."""
    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)
    graph = build_graph(nodes)

    result = await graph.ainvoke(initial_state("Giá biệt thự Vinhomes Ocean Park 3 phòng ngủ?", "s2"))

    assert "chưa có đủ dữ liệu" in result["answer"].lower()
    assert result["citations"] == []
