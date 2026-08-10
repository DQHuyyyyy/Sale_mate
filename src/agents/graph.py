"""Dựng LangGraph state machine cho agent.

Luồng:

    START → router ─┬─(cần tra tài liệu)→ retrieve → generate → guardrail → END
                    └─(không cần)────────────────→ generate → guardrail → END

State machine chứ không phải chain thẳng: router rẽ nhánh, và về sau còn thêm
vòng lặp (truy hồi lại khi độ phủ thấp) mà không phải viết lại cấu trúc.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.agents.contracts import LLMProvider
from src.agents.nodes.generate import GenerateNode
from src.agents.nodes.guardrail import GuardrailNode
from src.agents.nodes.retrieve import RetrieveNode
from src.agents.nodes.router import RouterNode
from src.agents.state import AgentState
from src.core.config import Settings
from src.rag.contracts import Retriever


def route_after_router(state: AgentState) -> str:
    """Có cần tra tài liệu không — quyết định nhánh đi tiếp."""
    if state.get("error"):
        return "generate"
    return "retrieve" if state.get("needs_retrieval") else "generate"


def build_nodes(
    llm: LLMProvider,
    retriever: Retriever,
    settings: Settings,
) -> dict[str, object]:
    """Tạo các node dùng chung cho cả graph lẫn đường streaming."""
    return {
        "router": RouterNode(llm, model=settings.llm_model_fast),
        "retrieve": RetrieveNode(retriever),
        "generate": GenerateNode(
            llm,
            model=settings.llm_model_answer,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        ),
        "guardrail": GuardrailNode(settings.coverage_threshold),
    }


def build_graph(nodes: dict[str, object]):
    """Dựng và compile graph từ các node đã tạo. Gọi một lần lúc app khởi động."""
    graph = StateGraph(AgentState)

    for name in ("router", "retrieve", "generate", "guardrail"):
        graph.add_node(name, nodes[name])

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieve": "retrieve", "generate": "generate"},
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()
