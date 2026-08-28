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


class TestQuyenTruyHoi:
    """Dây bẫy cho lỗ hổng phân quyền CHƯA nối xong.

    Nguyên tắc dự án là "phân quyền lọc tại tầng truy hồi, không lọc ở UI", và
    `RetrievalFilter.visibility` đã sẵn sàng nhận danh sách quyền thật. Thiếu vế
    còn lại: `ChatRequest` không mang danh tính người dùng, nên lõi AI không biết
    ai đang hỏi và `build_nodes` đành ghim cứng `["public"]`.

    Hôm nay vô hại vì mọi tài liệu trong kho đều `public`. Đó là một sự trùng
    hợp, không phải một cơ chế — nên hai test dưới đây canh cho nó không lặng lẽ
    hết đúng. Đọc chú thích ở `build_nodes` để biết ba bước làm nốt.
    """

    def test_truy_hoi_dang_ghim_cung_public(self, scripted_llm, settings) -> None:
        nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)

        assert nodes["retrieve"]._visibility == ["public"]

    def test_moi_tai_lieu_deu_public_cho_toi_khi_noi_duoc_quyen(self) -> None:
        """Thêm một tài liệu `internal` mà chưa nối quyền là nó lọt ra cho khách
        vãng lai NGAY, không dấu hiệu nào. Test này đỏ trước khi chuyện đó xảy
        ra; đừng sửa nó cho xanh, hãy làm nốt phần phân quyền."""
        from pathlib import Path

        from src.data.sources.knowledge_docs import load_knowledge_dir

        thu_muc = Path("data/raw/knowledge")
        if not thu_muc.is_dir():
            pytest.skip("Chưa có kho tài liệu trong repo này")

        noi_bo = [d.doc_id for d in load_knowledge_dir(thu_muc) if d.metadata.get("visibility") != "public"]

        assert noi_bo == [], (
            f"Tài liệu không phải public: {noi_bo}. Tầng truy hồi đang ghim cứng "
            "visibility=['public'] nên chúng không bao giờ được đọc — mà nếu ai đó "
            "nới điều kiện đó ra thì chúng lọt cho khách vãng lai. Làm nốt phân "
            "quyền theo chú thích ở build_nodes trước khi thêm tài liệu nội bộ."
        )
