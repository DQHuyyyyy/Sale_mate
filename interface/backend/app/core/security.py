"""Hash mật khẩu (bcrypt) và phát/giải mã JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# bcrypt chỉ dùng 72 byte đầu; cắt trước để mật khẩu dài không gây lỗi.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    payload = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        payload = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(payload, hashed.encode("utf-8"))
    except ValueError:
        # Hash trong DB sai định dạng — coi như không khớp, không làm sập request.
        return False


def create_access_token(user_id: int, username: str, role: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Trả payload nếu token hợp lệ, None nếu hết hạn hoặc chữ ký sai."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
