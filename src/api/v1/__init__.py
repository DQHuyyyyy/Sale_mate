"""Gom router phiên bản v1.

Thêm nhóm endpoint mới = tạo file trong thư mục này rồi include_router bên dưới.

Lõi AI chỉ phục vụ hai việc: health check và chat. Dữ liệu căn hộ do
`interface/backend` (cổng 8000) lo — nó đọc thẳng Supabase.
"""

from fastapi import APIRouter

from src.api.v1 import chat, designer, health

router = APIRouter()
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(designer.router)

__all__ = ["router"]
