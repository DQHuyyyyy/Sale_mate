"""State của LangGraph agent — dữ liệu chảy giữa các node.

Dùng TypedDict (LangGraph yêu cầu), total=False để mọi trường là optional.
Mỗi node CHỈ trả về những trường nó thay đổi, không trả nguyên state.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict

from src.data.contracts import Chunk
from src.models.chat import ChatMessage, Citation


class Intent(StrEnum):
    """Router phân loại câu hỏi vào một trong các nhánh này."""

    GENERAL = "general"  # Trả lời trực tiếp, không cần tra cứu
    DOCUMENT = "document"  # Cần RAG trên kho tài liệu
    LISTING = "listing"  # Tìm bất động sản / tin đăng
    PRICE = "price"  # Hỏi giá — phải lấy từ DB có cấu trúc
    LEGAL = "legal"  # Câu hỏi pháp lý
    DRAFT = "draft"  # Nhờ soạn nội dung (tin đăng, tin nhắn)


class AgentState(TypedDict, total=False):
    """Bộ nhớ làm việc của agent trong một lượt hỏi.

    Trường:
        query: Câu hỏi gốc của người dùng.
        history: Vài lượt trước để giữ ngữ cảnh.
        session_id: ID phiên hội thoại.
        intent: Kết quả phân loại của router.
        needs_retrieval: Router quyết định có phải tra tài liệu không.
        entities: Tiêu chí router rút được, ĐÃ giải tham chiếu bằng lịch sử —
            "20 căn đó" thành khoảng giá và phân khu thật. Rỗng ở lượt đầu vì
            không có gì để giải tham chiếu, và khi rỗng thì mọi tool rơi về đúng
            hành vi cũ. Xem `src/agents/thuc_the.py`.
        da_truy_hoi: Node retrieve ĐÃ chạy thật chưa. Khác `chunks` rỗng ở chỗ
            nó phân biệt "tìm rồi mà không có" với "chưa hề tìm" — plan cần
            phân biệt đó để không hỏi ngược người dùng khi chưa tra cứu lần nào.
        chunks: Các đoạn tài liệu đã truy hồi.
        coverage: Độ phủ truy hồi (0-1) — dưới ngưỡng thì phải từ chối.
        context: Chunk đã ghép thành text để nhét vào prompt.
        tool_context: Kết quả tool đã ghép thành text, tách khỏi `context` vì
            node retrieve chạy sau và ghi đè `context`.
        tool_citations: Nguồn từ tool (kind="db"), guardrail gộp vào citations.
        tools_ran: Tên các tool đã chạy — để stream báo cho người dùng biết
            trợ lý đang làm gì thay vì ngồi nhìn màn hình trống.
        tool_filters: Tiêu chí từng tool đã dùng, để giao diện đồng bộ bộ lọc
            trên trang tìm kiếm với thứ trợ lý vừa trả lời.
        tieu_chi_rong: Các bộ tiêu chí vừa tra và CHẮC CHẮN không có căn nào
            khớp. Tầng gợi ý đọc để không mời người dùng bấm vào ngõ cụt —
            "So sánh các căn 2PN, 3 vệ sinh ở Ocean Park 1" từng lọt ra giao
            diện trong khi kho không có căn 3 vệ sinh nào.
        plan_action: Quyết định của node plan: "act" · "answer" · "clarify"
            · "retrieve".
        plan_reason: Lý do ngắn gọn, hiện thẳng cho người dùng thấy agent
            đang nghĩ gì.
        plan_tool: Tool mà plan chọn gọi (chỉ có nghĩa khi plan_action="act").
        plan_args: Tham số cho tool đó.
        plan_options: Vài phương án trả lời sẵn kèm câu hỏi ngược, để người
            dùng bấm chọn thay vì phải gõ lại (chỉ có khi plan_action="clarify").
        iterations: Số vòng plan → act đã chạy. Có trần cứng để một câu hỏi xấu
            không đốt sạch quota.
        da_thu: Chữ ký các hành động đã thử — để nhận ra agent đang lặp lại
            chính nó và cắt sớm.
        leo_thang: Tên luật đã kích hoạt orchestrator (""=không leo thang). Ghi
            lại tên chứ không ghi bool để lúc hết ngân sách còn biết luật nào
            kéo chi phí lên. Xem `src/agents/leo_thang.py`.
        orchestrator_loi: Lý do orchestrator hỏng, nếu có. Có giá trị ở đây thì
            câu trả lời vẫn được sinh bình thường từ bằng chứng đã gom.
        orchestrator_token_vao / _ra / _cache: Token của riêng nhánh leo thang,
            để tính chi phí và chặn ngân sách ngày.
        answer: Câu trả lời cuối.
        citations: Nguồn kèm theo câu trả lời.
        is_sensitive: Có chứa giá/cam kết cần người duyệt không.
        error: Thông báo lỗi nếu có node nào hỏng.
        metadata: Số liệu phụ (token, độ trễ) để quan sát.
    """

    query: str
    history: list[ChatMessage]
    session_id: str

    intent: Intent
    needs_retrieval: bool
    da_truy_hoi: bool
    entities: dict[str, Any]

    chunks: list[Chunk]
    coverage: float
    context: str

    tool_context: str
    tool_citations: list[Citation]
    tools_ran: list[str]
    tool_filters: dict[str, Any]
    tieu_chi_rong: list[dict[str, Any]]

    plan_action: str
    plan_reason: str
    plan_tool: str
    plan_args: dict[str, Any]
    plan_options: list[str]
    iterations: int
    da_thu: list[str]

    leo_thang: str
    orchestrator_loi: str
    orchestrator_token_vao: int
    orchestrator_token_ra: int
    orchestrator_token_cache: int

    answer: str
    citations: list[Citation]
    is_sensitive: bool

    error: str
    metadata: dict[str, Any]


def initial_state(
    query: str,
    session_id: str,
    history: list[ChatMessage] | None = None,
) -> AgentState:
    """Tạo state khởi đầu cho một lượt hỏi."""
    return AgentState(
        query=query,
        session_id=session_id,
        history=history or [],
        chunks=[],
        citations=[],
        tool_context="",
        tool_citations=[],
        tools_ran=[],
        tool_filters={},
        tieu_chi_rong=[],
        iterations=0,
        da_thu=[],
        da_truy_hoi=False,
        plan_options=[],
        coverage=0.0,
        is_sensitive=False,
        metadata={},
    )
