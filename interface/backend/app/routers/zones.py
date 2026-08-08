from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.db import fetch_all
from app.core.deps import get_optional_user
from app.schemas.auth import CurrentUser
from app.schemas.zone import Tower, Zone

router = APIRouter(prefix="/api", tags=["zones"])


@router.get("/zones", response_model=list[Zone])
def list_zones(_: CurrentUser | None = Depends(get_optional_user)) -> list[Zone]:
    """Danh sách phân khu, kèm mã các tòa thuộc khu — dựng sơ đồ phân khu."""
    rows = fetch_all(
        """
        SELECT z.id, z.code, z.name, z.description, z.image_url,
               COALESCE(
                   array_agg(t.code ORDER BY t.code) FILTER (WHERE t.code IS NOT NULL),
                   '{}'
               ) AS towers
        FROM zones z
        LEFT JOIN towers t ON t.zone_id = z.id
        GROUP BY z.id, z.code, z.name, z.description, z.image_url
        ORDER BY z.code, z.name
        """
    )
    return [Zone(**row) for row in rows]


@router.get("/towers", response_model=list[Tower])
def list_towers(_: CurrentUser | None = Depends(get_optional_user)) -> list[Tower]:
    """Danh sách tòa để đổ vào dropdown bộ lọc."""
    rows = fetch_all(
        """
        SELECT t.id, t.code, t.name, t.zone_id, z.code AS zone_code, t.description
        FROM towers t
        LEFT JOIN zones z ON z.id = t.zone_id
        ORDER BY t.code
        """
    )
    return [Tower(**row) for row in rows]
