"""Test từng node của agent — nhanh, không gọi mạng."""

from __future__ import annotations

import pytest

from src.agents.nodes.base import BaseNode
from src.agents.nodes.generate import GenerateNode, build_messages
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE, GuardrailNode
from src.agents.nodes.retrieve import RetrieveNode
from src.agents.nodes.router import RouterNode
from src.agents.state import Intent, initial_state
from src.data.contracts import Chunk, RetrievalResult
from src.models.chat import MessageRole
from tests.conftest import FAKE_REPLY


class _BrokenNode(BaseNode):
    name = "broken"

    async def execute(self, state):
        raise RuntimeError("hỏng rồi")


class _StubRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    async def retrieve(self, query, *, filters=None, top_k=None, top_n=None):
        return self._result


# ---------------- BaseNode ----------------


@pytest.mark.asyncio
async def test_base_node_bat_loi_thay_vi_lam_dut_graph():
    result = await _BrokenNode()(initial_state("hỏi gì đó", "s1"))

    assert "hỏng rồi" in result["error"]


@pytest.mark.asyncio
async def test_base_node_ghi_lai_thoi_gian_chay(scripted_llm):
    result = await RouterNode(scripted_llm)(initial_state("Xin chào", "s1"))

    assert "router_ms" in result["metadata"]


# ---------------- Router ----------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Thủ tục sang tên sổ đỏ gồm những gì?", Intent.LEGAL),
        ("Giá căn hộ Cầu Giấy bao nhiêu?", Intent.PRICE),
        ("Viết tin đăng bán căn 2PN giúp mình", Intent.DRAFT),
        ("Tìm căn hộ 2PN dưới 4 tỷ", Intent.LISTING),
    ],
)
async def test_router_bat_intent_bang_tu_khoa(scripted_llm, query, expected):
    """Luật từ khoá chạy trước để khỏi tốn một lượt gọi LLM."""
    result = await RouterNode(scripted_llm)(initial_state(query, "s1"))

    assert result["intent"] == expected


@pytest.mark.asyncio
async def test_router_nhan_la_thi_roi_ve_general(scripted_llm):
    """LLM trả nhãn không hợp lệ thì router phải fallback, không được nổ."""
    result = await RouterNode(scripted_llm)(initial_state("Xin chào bạn", "s1"))

    assert result["intent"] == Intent.GENERAL
    assert result["needs_retrieval"] is False


# ---------------- Retrieve ----------------


@pytest.mark.asyncio
async def test_retrieve_bo_qua_khi_khong_can_tra_cuu():
    node = RetrieveNode(_StubRetriever(RetrievalResult()))
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = False

    result = await node(state)

    assert result["chunks"] == []
    assert result["context"] == ""


@pytest.mark.asyncio
async def test_retrieve_sinh_citation_tu_chunk():
    chunk = Chunk(
        id="c1",
        text="Chính sách chiết khấu 5%.",
        doc_id="doc-1",
        doc_title="Chính sách bán hàng",
        version="v2",
        page=3,
    )
    node = RetrieveNode(_StubRetriever(RetrievalResult(chunks=[chunk], coverage=0.9)))
    state = initial_state("Chiết khấu bao nhiêu?", "s1")
    state["needs_retrieval"] = True

    result = await node(state)

    assert result["coverage"] == 0.9
    assert result["citations"][0].doc_id == "doc-1"
    assert result["citations"][0].version == "v2"


# ---------------- Generate ----------------


def test_build_messages_khong_co_context_thi_giu_nguyen_cau_hoi():
    messages = build_messages(initial_state("Giá thế nào?", "s1"))

    assert messages[0].role == MessageRole.SYSTEM
    assert messages[-1].content == "Giá thế nào?"


def test_build_messages_co_context_thi_ep_grounding():
    state = initial_state("Giá thế nào?", "s1")
    state["context"] = "Giá bán 3,85 tỷ."

    messages = build_messages(state)

    assert "<ngu_canh>" in messages[-1].content
    assert "Giá bán 3,85 tỷ." in messages[-1].content


@pytest.mark.asyncio
async def test_generate_tra_ve_cau_tra_loi(scripted_llm):
    result = await GenerateNode(scripted_llm)(initial_state("Xin chào", "s1"))

    assert result["answer"] == FAKE_REPLY


# ---------------- Guardrail ----------------


@pytest.mark.asyncio
async def test_guardrail_tu_choi_khi_do_phu_thap():
    state = initial_state("Chính sách chiết khấu?", "s1")
    state["needs_retrieval"] = True
    state["chunks"] = []
    state["coverage"] = 0.1

    result = await GuardrailNode(0.35)(state)

    assert result["answer"] == INSUFFICIENT_MESSAGE
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_guardrail_cho_qua_khi_du_do_phu():
    chunk = Chunk(id="c1", text="nội dung", doc_id="d1")
    state = initial_state("Chính sách chiết khấu?", "s1")
    state["needs_retrieval"] = True
    state["chunks"] = [chunk]
    state["coverage"] = 0.8
    state["answer"] = "Chiết khấu 5%."

    result = await GuardrailNode(0.35)(state)

    assert "answer" not in result


@pytest.mark.asyncio
async def test_guardrail_gan_co_nhay_cam_khi_co_gia_kem_cam_ket():
    state = initial_state("Soạn tin gửi khách", "s1")
    state["answer"] = "Căn này 3,85 tỷ, bên em cam kết giữ chỗ cho anh."

    result = await GuardrailNode(0.35)(state)

    assert result["is_sensitive"] is True


@pytest.mark.asyncio
async def test_guardrail_khong_gan_co_khi_chi_co_gia():
    state = initial_state("Giá bao nhiêu", "s1")
    state["answer"] = "Mặt bằng giá khu vực khoảng 56 tr/m²."

    result = await GuardrailNode(0.35)(state)

    assert result["is_sensitive"] is False
