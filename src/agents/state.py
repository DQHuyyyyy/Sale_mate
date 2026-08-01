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
        chunks: Các đoạn tài liệu đã truy hồi.
        coverage: Độ phủ truy hồi (0-1) — dưới ngưỡng thì phải từ chối.
        context: Chunk đã ghép thành text để nhét vào prompt.
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

    chunks: list[Chunk]
    coverage: float
    context: str

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
        coverage=0.0,
        is_sensitive=False,
        metadata={},
    )
