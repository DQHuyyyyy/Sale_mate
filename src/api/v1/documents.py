"""Đọc tài liệu kiến thức — thứ trợ lý trích dẫn, cho người đọc kiểm chứng.

Trích nguồn chỉ có giá trị khi bấm vào xem được. Trước file này, dòng "Nguồn"
là chữ chết: người đọc phải tin lời trợ lý mà không có cách nào đối chiếu.

## Vì sao đọc từ FILE chứ không từ Qdrant

Qdrant mới là thứ trợ lý thật sự đọc, nên đọc từ đó thì đúng nghĩa "hiện đúng
bản đã dùng". Nhưng `VectorStore` Protocol chỉ có `search`/`delete_by_doc`/
`count` — không có hàm liệt kê tài liệu hay lấy nguyên văn theo `doc_id`, và
`data/contracts.py` là file ĐÓNG BĂNG: muốn thêm phải mở PR contract riêng, cả
team review.

File nguồn cho đúng cùng một nội dung mà không phải đụng hợp đồng: `doc_id` sinh
từ chính tên file (`knowledge:{path.stem}`), nên định danh khớp một-đối-một với
thứ Qdrant đang giữ.

⚠️ ĐÁNH ĐỔI: sửa file mà quên `python -m src.cli ingest` thì trang này hiện bản
mới trong khi trợ lý vẫn đọc bản cũ. Nên response luôn kèm `version` lấy từ
front-matter — lệch phiên bản là nhìn thấy được, không phải đoán.

Route KHÔNG tự kiểm quyền: lõi AI không có khái niệm người dùng. `interface/
backend` mới là nơi chặn, và nó chỉ mở cho tài khoản đã đăng nhập.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.core.logging import get_logger
from src.data.sources.knowledge_docs import load_knowledge_dir

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


class TaiLieuTomTat(BaseModel):
    """Một dòng trong danh sách. KHÔNG chở nội dung — danh sách 11 tài liệu mà
    kèm toàn văn là vài chục KB cho một màn hình chỉ hiện tiêu đề."""

    doc_id: str
    title: str
    section: str
    version: str
    so_ky_tu: int


class TaiLieuDayDu(TaiLieuTomTat):
    noi_dung: str
    source_url: str


def _doc_het() -> dict[str, object]:
    """Nạp mọi file .md, bỏ qua file hỏng thay vì làm sập cả danh sách.

    Một file sai front-matter không được che mất mười file đúng — nhưng vẫn ghi
    WARNING, vì file hỏng nghĩa là `ingest` cũng đang bỏ sót nó.
    """
    ket_qua: dict[str, object] = {}
    try:
        docs = load_knowledge_dir()
    except ValueError as exc:
        logger.warning("Có file tài liệu sai định dạng, danh sách sẽ thiếu: %s", exc)
        return ket_qua
    for d in docs:
        ket_qua[d.doc_id] = d
    return ket_qua


@router.get("", response_model=list[TaiLieuTomTat])
async def danh_sach() -> list[TaiLieuTomTat]:
    """Toàn bộ tài liệu trợ lý có thể trích, sắp theo tiêu đề."""
    docs = _doc_het()
    return sorted(
        (
            TaiLieuTomTat(
                doc_id=d.doc_id,
                title=d.title,
                section=str(d.metadata.get("section") or ""),
                version=str(d.metadata.get("version") or ""),
                so_ky_tu=len(d.text),
            )
            for d in docs.values()  # type: ignore[union-attr]
        ),
        key=lambda x: x.title,
    )


@router.get("/{doc_id:path}", response_model=TaiLieuDayDu)
async def chi_tiet(doc_id: str) -> TaiLieuDayDu:
    """Toàn văn một tài liệu.

    `:path` vì `doc_id` chứa dấu hai chấm (`knowledge:phap-ly-thu-tuc`) và cả
    khoảng trắng lẫn dấu tiếng Việt — để mặc định thì Starlette cắt ở dấu `/`
    và tên có dấu bị hỏng.
    """
    d = _doc_het().get(doc_id)
    if d is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không có tài liệu {doc_id}.",
        )
    return TaiLieuDayDu(
        doc_id=d.doc_id,  # type: ignore[union-attr]
        title=d.title,  # type: ignore[union-attr]
        section=str(d.metadata.get("section") or ""),  # type: ignore[union-attr]
        version=str(d.metadata.get("version") or ""),  # type: ignore[union-attr]
        so_ky_tu=len(d.text),  # type: ignore[union-attr]
        noi_dung=d.text,  # type: ignore[union-attr]
        source_url=str(d.metadata.get("source_url") or ""),  # type: ignore[union-attr]
    )
