from __future__ import annotations

from pydantic import BaseModel


class Tower(BaseModel):
    id: int
    code: str
    name: str | None = None
    zone_id: int | None = None
    zone_code: str | None = None
    description: str | None = None


class Zone(BaseModel):
    id: int
    code: str | None = None
    name: str
    description: str | None = None
    image_url: str | None = None
    towers: list[str] = []
