"""Endpoint dữ liệu trang portal.

Dữ liệu hiện là stub trong bộ nhớ, nhưng FE gọi API thật ngay từ đầu — khi có
DB chỉ đổi implementation ở src/bootstrap.py, FE không phải sửa gì.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.api.deps import PortalDep
from src.models.portal import Demand, Listing, ListingType, MarketStats, Project

router = APIRouter(tags=["portal"])


@router.get("/listings", response_model=list[Listing], summary="Danh sách tin đăng")
async def list_listings(
    repo: PortalDep,
    listing_type: ListingType | None = Query(default=None, description="Lọc theo tab: sale | rent | transfer"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Listing]:
    return await repo.list_listings(listing_type=listing_type, limit=limit)


@router.get("/projects", response_model=list[Project], summary="Dự án nổi bật")
async def list_projects(
    repo: PortalDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Project]:
    return await repo.list_projects(limit=limit)


@router.get("/demands", response_model=list[Demand], summary="Nhu cầu người dùng")
async def list_demands(
    repo: PortalDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Demand]:
    return await repo.list_demands(limit=limit)


@router.get("/market", response_model=MarketStats, summary="Thống kê thị trường hôm nay")
async def market_stats(repo: PortalDep) -> MarketStats:
    return await repo.market_stats()
