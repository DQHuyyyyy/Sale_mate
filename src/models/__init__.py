"""DTO dùng chung — HỢP ĐỒNG giữa 4 module (data · agents · api · frontend).

⚠️ File trong thư mục này bị ĐÓNG BĂNG. Muốn thêm/sửa trường: mở PR riêng vào
develop để cả team review, không sửa lẫn trong PR tính năng.
"""

from src.models.chat import (
    ChatEvent,
    ChatEventType,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Citation,
    MessageRole,
)
from src.models.common import ErrorDetail, ErrorResponse, HealthResponse
from src.models.portal import (
    Demand,
    Listing,
    ListingType,
    MarketBar,
    MarketStats,
    Page,
    Project,
    PropertyKind,
)

__all__ = [
    "ChatEvent",
    "ChatEventType",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "Demand",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "Listing",
    "ListingType",
    "MarketBar",
    "MarketStats",
    "MessageRole",
    "Page",
    "Project",
    "PropertyKind",
]
