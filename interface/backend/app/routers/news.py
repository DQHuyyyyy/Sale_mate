"""Endpoint lấy tin tức thị trường bất động sản — công khai, không cần đăng nhập."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.news_service import get_real_estate_news_async

router = APIRouter(prefix="/api/news", tags=["news"])


class NewsItem(BaseModel):
    id: str
    title: str
    link: str
    image_url: str = ""
    source: str
    source_name: str
    pub_date: str = ""
    summary: str = ""


class NewsResponse(BaseModel):
    total: int
    items: list[NewsItem] = Field(default_factory=list)


@router.get("", response_model=NewsResponse)
async def list_news(
    limit: int = Query(default=10, ge=1, le=50, description="Số lượng tin muốn lấy"),
    refresh: bool = Query(default=False, description="Bắt buộc làm mới cache"),
) -> dict[str, Any]:
    """Lấy danh sách tin tức thị trường bất động sản mới nhất."""
    items = await get_real_estate_news_async(limit=limit, force_refresh=refresh)
    return {
        "total": len(items),
        "items": items,
    }
