"""DTO dùng chung — HỢP ĐỒNG giữa lõi AI và API sản phẩm.

⚠️ File trong thư mục này bị ĐÓNG BĂNG. Muốn thêm/sửa trường: mở PR riêng vào
develop để cả team review, không sửa lẫn trong PR tính năng.

Dữ liệu căn hộ (Listing/Project/MarketStats) ĐÃ BỎ khỏi đây — lõi AI không phục
vụ trang portal nữa. Frontend gọi `interface/backend` (cổng 8000), nơi đọc thẳng
`salemate_v1` trên Supabase. Xem `interface/backend/app/schemas/apartment.py`.
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

__all__ = [
    "ChatEvent",
    "ChatEventType",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "MessageRole",
]
