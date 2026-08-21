"""Upload file lên Supabase Storage.

Chỉ backend gọi được — dùng SUPABASE_SERVICE_ROLE_KEY (bỏ qua RLS), key này
tuyệt đối không đi ra frontend.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import PurePosixPath

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class StorageError(RuntimeError):
    """Upload thất bại — router bắt lại và trả lỗi có nội dung cho người dùng."""


def safe_file_name(original: str | None) -> str:
    """Bỏ dấu/khoảng trắng khỏi tên file và thêm hậu tố ngẫu nhiên chống trùng."""
    name = PurePosixPath(original or "file").name
    cleaned = _SAFE_NAME.sub("-", name).strip("-") or "file"
    suffix = uuid.uuid4().hex[:8]
    if "." in cleaned:
        stem, ext = cleaned.rsplit(".", 1)
        return f"{stem}-{suffix}.{ext.lower()}"
    return f"{cleaned}-{suffix}"


def public_url(storage_path: str) -> str:
    base = settings.supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/public/{settings.supabase_bucket}/{storage_path}"


def upload_bytes(storage_path: str, content: bytes, content_type: str | None) -> str:
    """Đẩy file lên bucket, trả public URL. Ném StorageError nếu hỏng."""
    if not settings.storage_enabled:
        raise StorageError(
            "Chưa cấu hình Supabase Storage. Điền SUPABASE_URL và "
            "SUPABASE_SERVICE_ROLE_KEY trong .env ở gốc repo rồi khởi động lại backend."
        )

    base = settings.supabase_url.rstrip("/")
    url = f"{base}/storage/v1/object/{settings.supabase_bucket}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": content_type or "application/octet-stream",
        "x-upsert": "true",
    }

    try:
        response = httpx.post(url, content=content, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được Supabase Storage")
        raise StorageError("Không kết nối được Supabase Storage. Thử lại sau ít phút.") from exc

    if response.status_code >= 400:
        logger.error("Supabase Storage trả %s: %s", response.status_code, response.text[:500])
        raise StorageError(
            f"Supabase Storage từ chối file (HTTP {response.status_code}). "
            f"Kiểm tra bucket '{settings.supabase_bucket}' đã tồn tại chưa."
        )

    return public_url(storage_path)


def delete_object(storage_path: str) -> None:
    """Xoá một object khỏi bucket. Ném StorageError nếu hỏng.

    Chỉ gọi được cho ảnh ĐÃ nằm trên Supabase Storage (`storage_path` khác NULL).
    Ảnh cũ nhập từ Google Drive không có object nào ở đây để xoá.
    """
    if not settings.storage_enabled:
        raise StorageError(
            "Chưa cấu hình Supabase Storage. Điền SUPABASE_URL và "
            "SUPABASE_SERVICE_ROLE_KEY trong .env ở gốc repo rồi khởi động lại backend."
        )

    base = settings.supabase_url.rstrip("/")
    url = f"{base}/storage/v1/object/{settings.supabase_bucket}/{storage_path}"
    headers = {"Authorization": f"Bearer {settings.supabase_service_role_key}"}

    try:
        response = httpx.delete(url, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được Supabase Storage để xoá %s", storage_path)
        raise StorageError("Không kết nối được Supabase Storage. Thử lại sau ít phút.") from exc

    # 404 = file đã không còn ở đó. Đích đến là "object biến mất", và nó đã biến
    # mất rồi — báo lỗi ở đây chỉ làm người dùng bấm lại một việc đã xong.
    if response.status_code >= 400 and response.status_code != 404:
        logger.error("Supabase Storage trả %s khi xoá: %s", response.status_code, response.text[:500])
        raise StorageError(f"Supabase Storage từ chối xoá file (HTTP {response.status_code}).")
