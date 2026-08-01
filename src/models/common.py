"""DTO dùng chung: health check và khuôn dạng lỗi."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Khuôn dạng lỗi thống nhất cho mọi endpoint.

    FE chỉ cần đọc error.message để hiển thị — luôn là tiếng Việt.
    """

    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"] = "healthy"
    version: str = "0.1.0"
    environment: str = "development"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checks: dict[str, str] = Field(default_factory=dict)
