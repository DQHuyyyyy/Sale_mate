"""Dependency dùng chung: lấy user từ JWT, chặn route admin.

Đây là nơi DUY NHẤT thực thi phân quyền. Frontend ẩn nút chỉ là UX.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.db import fetch_one
from app.core.security import decode_access_token
from app.schemas.auth import CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Đăng nhập lại để tiếp tục.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_ERROR

    payload = decode_access_token(credentials.credentials)
    if payload is None or "user_id" not in payload:
        raise _CREDENTIALS_ERROR

    # Đọc lại từ DB: user bị xoá, đổi role hoặc bị vô hiệu hoá thì token cũ mất
    # hiệu lực ngay lần gọi API kế tiếp, không phải chờ token hết hạn.
    row = fetch_one(
        """
        SELECT id, username, full_name, role, phone, email, avatar_url,
               is_active, created_at
        FROM users WHERE id = %s
        """,
        (payload["user_id"],),
    )
    if row is None:
        raise _CREDENTIALS_ERROR

    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đã bị vô hiệu hoá. Liên hệ quản trị viên để mở lại.",
        )

    return CurrentUser(**row)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser | None:
    """Dùng cho route công khai: có token hợp lệ thì trả user, không thì trả None.

    Khác `get_current_user` ở chỗ KHÔNG ném lỗi khi thiếu token — khách vãng lai
    vẫn xem được căn hộ và phân khu. Token sai hoặc hết hạn cũng coi như khách,
    không chặn, vì mấy trang này vốn không cần đăng nhập.

    Chỉ gắn vào route thực sự công khai. Route nào cần danh tính thì vẫn phải
    dùng `get_current_user` / `require_admin`.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chức năng này chỉ dành cho quản trị viên.",
        )
    return current_user


def require_sale(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "sale":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chức năng này chỉ dành cho nhân viên sale.",
        )
    return current_user


def require_sale_hoac_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Sale làm việc với lead, admin giám sát — cả hai đều vào được.

    Không dùng `require_sale` cho lead đặt cọc: nó chặn cả admin, mà admin là
    người duy nhất nhìn được toàn cảnh trạng thái căn. Cũng không dùng
    `require_admin`: sale mới là người nhận cọc.
    """
    if current_user.role not in ("sale", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chức năng này dành cho nhân viên sale và quản trị viên.",
        )
    return current_user
