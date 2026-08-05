from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.db import fetch_one
from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    row = fetch_one(
        """
        SELECT id, username, password_hash, full_name, role, phone, email,
               avatar_url, is_active, created_at
        FROM users WHERE username = %s
        """,
        (payload.username,),
    )

    # Thông báo giống nhau cho "sai user" và "sai mật khẩu" — không để dò tài khoản.
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng.",
        )

    # Mật khẩu đúng nhưng tài khoản bị tắt — nói thẳng để người dùng biết hỏi ai,
    # thay vì để họ nghĩ mình gõ sai mật khẩu.
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đã bị vô hiệu hoá. Liên hệ quản trị viên để mở lại.",
        )

    row.pop("password_hash")
    user = UserPublic(**row)
    token = create_access_token(user.id, user.username, user.role)
    return LoginResponse(token=token, user=user)


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**current_user.model_dump())
