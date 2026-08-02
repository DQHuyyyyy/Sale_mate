"""Gom router phiên bản v1.

Thêm nhóm endpoint mới = tạo file trong thư mục này rồi include_router bên dưới.
"""

from fastapi import APIRouter

from src.api.v1 import chat, health, portal

router = APIRouter()
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(portal.router)

__all__ = ["router"]
