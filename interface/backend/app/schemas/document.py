from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=50)
    file_url: str | None = None


class Document(BaseModel):
    id: int
    title: str
    description: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    category: str | None = None
    uploaded_by: int | None = None
    uploaded_by_name: str | None = None
    created_at: datetime | None = None
