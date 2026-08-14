"""Dựng LangGraph state machine cho agent.

Luồng:

    START → router → tools ─┬─(cần tra tài liệu)→ retrieve → generate → guardrail → END
                            └─(không cần)────────────────→ generate → guardrail → END

State machine chứ không phải chain thẳng: router rẽ nhánh, và về sau còn thêm
vòng lặp (truy hồi lại khi độ phủ thấp) mà không phải viết lại cấu trúc.

`tools` nằm trên đường đi CHUNG chứ không phải một nhánh rẽ, và tự thoát ngay
khi không có tool nào nhận nhãn hiện tại. Nhờ vậy thêm tool mới chỉ là thêm một
file trong `agents/tools/` — không đụng file này. Đổi lại, câu chào hỏi đi qua
thêm một node rỗng; cái giá đó rẻ hơn nhiều so với việc mỗi tool mới lại phải
sửa bảng điều hướng.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.agents.contracts import LLMProvider
from src.agents.nodes.act import ActNode
from src.agents.nodes.generate import GenerateNode
from src.agents.nodes.guardrail import GuardrailNode
from src.agents.nodes.plan import ACT, RETRIEVE, PlanNode
from src.agents.nodes.retrieve import RetrieveNode
from src.agents.nodes.router import RouterNode
from src.agents.nodes.tools import ToolsNode
from src.agents.state import AgentState
from src.core.config import Settings
from src.rag.contracts import Retriever

# Các node chạy TRƯỚC khi sinh chữ, theo đúng thứ tự. Khai một chỗ duy nhất vì
# đường stream (agents/service.py) phải chạy lại đúng dãy này để lấy context —
# trước đây nó tự liệt kê router+retrieve và âm thầm bỏ sót node tools mới thêm.
CONTEXT_NODES: tuple[str, ...] = ("router", "tools", "retrieve")


def route_after_tools(state: AgentState) -> str:
    """Có cần tra tài liệu không — quyết định nhánh đi tiếp."""
    if state.get("error"):
        return "generate"
    return "retrieve" if state.get("needs_retrieval") else "generate"


def route_after_plan(state: AgentState) -> str:
    """Kế hoạch nói gì thì đi đó. Lỗi hoặc nhãn lạ đều về generate.

    Vòng lặp đóng ở `act` và ở `retrieve` — cả hai đều có cạnh quay về `plan`.
    Trần lần lặp nằm trong chính `plan`, một chỗ chặn duy nhất không thể quên.
    Riêng `retrieve` không cần trần: `plan` chỉ chọn nó khi chưa truy hồi lần
    nào, mà node retrieve bật `da_truy_hoi` ngay lần chạy đầu.
    """
    if state.get("error"):
        return "generate"
    action = state.get("plan_action")
    if action == ACT:
        return "act"
    if action == RETRIEVE:
        return "retrieve"
    return "generate"


def build_nodes(
    llm: LLMProvider,
    retriever: Retriever,
    settings: Settings,
) -> dict[str, object]:
    """Tạo các node dùng chung cho cả graph lẫn đường streaming."""
    nodes: dict[str, object] = {
        "router": RouterNode(llm, model=settings.llm_model_fast),
        "tools": ToolsNode(),
        "retrieve": RetrieveNode(retriever),
        "generate": GenerateNode(
            llm,
            model=settings.llm_model_answer,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        ),
        "guardrail": GuardrailNode(settings.coverage_threshold),
    }

    if settings.enable_agent_loop:
        nodes["plan"] = PlanNode(
            llm,
            max_iterations=settings.agent_max_iterations,
            model=settings.llm_model_fast,
        )
        nodes["act"] = ActNode()

    return nodes


def build_graph(nodes: dict[str, object]):
    """Dựng và compile graph từ các node đã tạo. Gọi một lần lúc app khởi động.

    Có vòng lặp agent hay không tuỳ `nodes` — `build_nodes` chỉ tạo plan/act khi
    `enable_agent_loop` bật. Nhờ vậy tắt cờ là quay về đúng đường tất định cũ,
    không phải giữ hai bản graph song song.

        tắt:  router → tools ─┬→ retrieve → generate → guardrail → END
                              └──────────→ generate → ...

        bật:  router → tools ─┬→ retrieve ─┐
                              └────────────┴→ plan ─┬→ act ──────┐
                                              ↑     ├→ retrieve ─┤
                                              └─────┴────────────┘
                                                    └→ generate → guardrail → END
    """
    graph = StateGraph(AgentState)
    co_vong_lap = "plan" in nodes and "act" in nodes

    ten_node = ["router", "tools", "retrieve", "generate", "guardrail"]
    if co_vong_lap:
        ten_node += ["plan", "act"]
    for name in ten_node:
        graph.add_node(name, nodes[name])

    graph.add_edge(START, "router")
    graph.add_edge("router", "tools")

    # Đích sau khi gom xong context: có vòng lặp thì để plan quyết, không thì
    # sinh chữ luôn.
    sau_context = "plan" if co_vong_lap else "generate"
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {"retrieve": "retrieve", "generate": sau_context},
    )
    graph.add_edge("retrieve", sau_context)

    if co_vong_lap:
        graph.add_conditional_edges(
            "plan",
            route_after_plan,
            {"act": "act", "retrieve": "retrieve", "generate": "generate"},
        )
        # Chạy xong quay lại plan để nó nhìn bằng chứng mới rồi quyết tiếp.
        graph.add_edge("act", "plan")

    graph.add_edge("generate", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()
