from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserPublic(BaseModel):
    """Thông tin user trả ra ngoài — KHÔNG bao giờ kèm password_hash."""

    id: int
    username: str
    full_name: str
    role: str
    phone: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class CurrentUser(UserPublic):
    pass


class LoginResponse(BaseModel):
    token: str
    user: UserPublic


class UserCreate(BaseModel):
    """Admin tạo tài khoản sale.

    Không có trường `role` — mọi tài khoản tạo qua đây đều là `sale`. Muốn thêm
    admin thì tạo bằng `scripts/seed_users.py`, không mở qua API.
    """

    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=6, max_length=200)
    full_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)


class UserActiveUpdate(BaseModel):
    """Bật / tắt tài khoản. Tắt rồi vẫn giữ nguyên lịch sử bán."""

    is_active: bool
