"""Cầu nối sang kho tài liệu của lõi AI — để trích nguồn bấm vào xem được.

Tài liệu nằm ở lõi AI (`src/`) chứ không ở database sản phẩm: đó là thứ trợ lý
đọc để trả lời, và nó phải là MỘT bản duy nhất. Sao chép sang Postgres để portal
đọc cho tiện là dựng nguồn thứ hai — đúng lỗi migration 005 đã trả giá với bảng
`inventory_units`.

Router này chỉ làm hai việc: **chặn quyền** rồi **dẫn ống**. Lõi AI không có
khái niệm người dùng, nên nơi duy nhất kiểm được là đây.

Khác `/api/chat` ở đúng một điểm: chat mở cho khách vãng lai, còn tài liệu thì
**bắt đăng nhập**. Bảng `documents` cũ (tài liệu admin tự đăng) giữ nguyên ở
`routers/documents.py`, không liên quan.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.deps import get_current_user
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/api/tai-lieu", tags=["tai-lieu"])


async def _goi_loi_ai(duong_dan: str) -> object:
    """Gọi lõi AI, đổi mọi lỗi mạng thành 502 có thông điệp đọc được."""
    url = f"{settings.ai_core_url.rstrip('/')}/api/v1/documents{duong_dan}"
    # Khoá dịch vụ, cùng khuôn với `services/chat.py`. Lõi AI có URL công khai
    # nên nó chặn request không cầm khoá — kể cả đường tài liệu.
    headers = {"X-API-Key": settings.ai_core_api_key} if settings.ai_core_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=settings.ai_core_timeout) as client:
            r = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Chưa kết nối được kho tài liệu. Thử lại sau ít phút.",
        ) from exc

    if r.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu này.")
    if r.status_code >= status.HTTP_400_BAD_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kho tài liệu trả về lỗi. Báo quản trị viên giúp mình.",
        )
    return r.json()


@router.get("")
async def danh_sach(_: CurrentUser = Depends(get_current_user)) -> object:
    """Danh sách tài liệu trợ lý có thể trích. Phải đăng nhập."""
    return await _goi_loi_ai("")


@router.get("/{doc_id:path}")
async def chi_tiet(doc_id: str, _: CurrentUser = Depends(get_current_user)) -> object:
    """Toàn văn một tài liệu — đích của nút trích nguồn.

    `:path` vì `doc_id` là `knowledge:phap-ly-thu-tuc`, có dấu hai chấm và có
    thể có khoảng trắng lẫn dấu tiếng Việt.
    """
    return await _goi_loi_ai(f"/{doc_id}")
