from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.db import fetch_all, get_conn
from app.core.deps import get_current_user, require_admin
from app.schemas.auth import CurrentUser
from app.schemas.document import Document
from app.services.storage import StorageError, safe_file_name, upload_bytes

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_FILE_BYTES = 20 * 1024 * 1024


@router.get("", response_model=list[Document])
def list_documents(_: CurrentUser = Depends(get_current_user)) -> list[Document]:
    rows = fetch_all(
        """
        SELECT d.id, d.title, d.description, d.file_url, d.file_name, d.category,
               d.uploaded_by, u.full_name AS uploaded_by_name, d.created_at
        FROM documents d
        LEFT JOIN users u ON u.id = d.uploaded_by
        ORDER BY d.created_at DESC
        """
    )
    return [Document(**row) for row in rows]


@router.post("", response_model=Document, status_code=status.HTTP_201_CREATED)
async def create_document(
    title: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None),
    category: str | None = Form(default=None, max_length=50),
    file_url: str | None = Form(default=None, description="Dùng khi tài liệu đã có link sẵn"),
    file: UploadFile | None = File(default=None),
    current_user: CurrentUser = Depends(require_admin),
) -> Document:
    """Thêm tài liệu (admin).

    Gửi multipart: hoặc đính kèm `file` (backend đẩy lên Supabase Storage), hoặc
    điền `file_url` nếu tài liệu đã có link sẵn.
    """
    if file is None and not file_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cần chọn file tải lên hoặc điền đường dẫn tài liệu.",
        )

    file_name = None
    if file is not None:
        content = await file.read()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File lớn hơn 20MB. Nén lại hoặc chia nhỏ rồi thử lại.",
            )
        storage_path = f"documents/{safe_file_name(file.filename)}"
        try:
            file_url = upload_bytes(storage_path, content, file.content_type)
        except StorageError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        file_name = file.filename

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (title, description, file_url, file_name, category, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, title, description, file_url, file_name, category,
                      uploaded_by, created_at
            """,
            (title, description, file_url, file_name, category, current_user.id),
        )
        row = cur.fetchone()

    return Document(**row, uploaded_by_name=current_user.full_name)
