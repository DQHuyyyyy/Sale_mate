from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors

from app.core.db import fetch_all, fetch_one, get_conn
from app.core.deps import require_admin
from app.core.security import hash_password
from app.schemas.auth import CurrentUser, UserActiveUpdate, UserCreate, UserPublic

router = APIRouter(prefix="/api/users", tags=["users"])

USER_COLUMNS = """
    id, username, full_name, role, phone, email, avatar_url, is_active, created_at
"""


def _load_user(user_id: int) -> dict:
    row = fetch_one(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tài khoản này. Có thể ai đó vừa xoá, tải lại danh sách.",
        )
    return row


@router.get("", response_model=list[UserPublic])
def list_users(
    role: str | None = Query(default=None, description="Lọc theo vai trò: admin | sale"),
    _: CurrentUser = Depends(require_admin),
) -> list[UserPublic]:
    if role is not None and role not in ("admin", "sale"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role chỉ nhận giá trị 'admin' hoặc 'sale'.",
        )

    sql = f"SELECT {USER_COLUMNS} FROM users"
    params: tuple = ()
    if role:
        sql += " WHERE role = %s"
        params = (role,)
    # Tài khoản đang hoạt động lên trước, rồi xếp theo tên.
    sql += " ORDER BY is_active DESC, full_name"

    return [UserPublic(**row) for row in fetch_all(sql, params)]


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: UserCreate,
    _: CurrentUser = Depends(require_admin),
) -> UserPublic:
    """Tạo tài khoản sale (admin).

    Vai trò cố định là 'sale' — API này không tạo được admin.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO users (username, password_hash, full_name, role, phone, email)
                VALUES (%s, %s, %s, 'sale', %s, %s)
                RETURNING {USER_COLUMNS}
                """,
                (
                    payload.username,
                    hash_password(payload.password),
                    payload.full_name,
                    payload.phone or None,
                    payload.email or None,
                ),
            )
            row = cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tên đăng nhập '{payload.username}' đã có người dùng. Chọn tên khác.",
        ) from exc

    return UserPublic(**row)


@router.patch("/{user_id}", response_model=UserPublic)
def set_user_active(
    user_id: int,
    payload: UserActiveUpdate,
    current_user: CurrentUser = Depends(require_admin),
) -> UserPublic:
    """Bật / tắt tài khoản sale (admin).

    Tắt tài khoản KHÔNG xoá dữ liệu: lịch sử bán của người đó vẫn nằm nguyên
    trong báo cáo "Căn đã bán toàn hệ thống". Bật lại được bất cứ lúc nào.
    """
    target = _load_user(user_id)

    if target["id"] == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không tự vô hiệu hoá tài khoản của chính mình được.",
        )
    if target["role"] != "sale":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Chỉ bật/tắt được tài khoản sale. Tài khoản quản trị phải sửa trực tiếp trong database."),
        )

    if target["is_active"] == payload.is_active:
        return UserPublic(**target)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE users SET is_active = %s WHERE id = %s RETURNING {USER_COLUMNS}",
            (payload.is_active, user_id),
        )
        row = cur.fetchone()

    return UserPublic(**row)
