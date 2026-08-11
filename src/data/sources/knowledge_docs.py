"""Nạp tài liệu kiến thức chung (chính sách, thủ tục, tiện ích...) dạng Markdown.

Khác CSV (tồn kho có cấu trúc) và HTML crawl (tin đăng bên thứ 3) — đây là
văn bản do team tự viết/tổng hợp (chính sách bán hàng, tiến độ thanh toán,
pháp lý, tiện ích...). Mỗi file bắt buộc khai front-matter title/section/
visibility rõ ràng — không suy luận ngầm từ tên file hay thư mục, để tránh
gắn nhầm quyền truy cập cho tài liệu nhạy cảm (chính sách chiết khấu, giá).

Quy ước front-matter (nằm giữa 2 dòng `---` ở đầu file):
    title: Tên tài liệu
    section: Nhóm nội dung, vd "Chính sách bán hàng"
    visibility: internal | public
    project: (tuỳ chọn) Dự án cụ thể tài liệu áp dụng, vd "Vinhomes Ocean Park 2
        (The Empire)". Không khai thì mặc định "Vinhomes Ocean Park Gia Lâm"
        (OCP1) — giữ tương thích ngược với các file cũ viết trước khi dự án mở
        rộng sang OCP2/OCP3.

Vì sao cần `project`: chính sách/giá/tiến độ khác nhau theo TỪNG dự án
(OCP1/OCP2/OCP3) — trộn chung một "project" mặc định sẽ khiến RetrievalFilter
không lọc được, và câu hỏi về OCP2 có thể lẫn số liệu OCP1. Xem
`RetrievalFilter.project` ở `src/data/contracts.py`.

File nguồn nằm ở data/raw/knowledge/ (bị .gitignore — mỗi máy tự có, xem
README/hướng dẫn nội bộ).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from src.data.contracts import LoadedDocument

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KNOWLEDGE_DIR = REPO_ROOT / "data" / "raw" / "knowledge"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_VALID_VISIBILITY = {"internal", "public"}
_REQUIRED_FRONTMATTER_KEYS = {"title", "section", "visibility"}
_DEFAULT_PROJECT = "Vinhomes Ocean Park Gia Lâm"  # OCP1 — mặc định cho file cũ chưa khai "project"


def _parse_frontmatter(raw: str, filename: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{filename}: thiếu front-matter (--- ... ---) ở đầu file")

    header, body = match.groups()
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()

    missing = _REQUIRED_FRONTMATTER_KEYS - meta.keys()
    if missing:
        raise ValueError(f"{filename}: front-matter thiếu khoá bắt buộc {sorted(missing)}")
    if meta["visibility"] not in _VALID_VISIBILITY:
        raise ValueError(f"{filename}: visibility phải là 'internal' hoặc 'public', không phải {meta['visibility']!r}")

    return meta, body.strip()


def load_knowledge_file(path: Path) -> LoadedDocument:
    """Đọc 1 file .md kiến thức chung thành LoadedDocument.

    Raise ValueError nếu thiếu/sai front-matter, hoặc nếu nội dung không mở
    đầu bằng heading H1 đúng `title` khai trong front-matter — thà báo lỗi
    sớm còn hơn ingest một tài liệu gắn nhầm quyền truy cập, hoặc thiếu
    heading chuẩn (yêu cầu bắt buộc của luồng xử lý dữ liệu).
    """
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw, path.name)

    expected_heading = f"# {meta['title']}"
    first_line = body.splitlines()[0] if body else ""
    if first_line != expected_heading:
        raise ValueError(f"{path.name}: nội dung phải mở đầu bằng '{expected_heading}' (heading H1 khớp title)")

    return LoadedDocument(
        doc_id=f"knowledge:{path.stem}",
        title=meta["title"],
        text=body,
        source_path=str(path),
        metadata={
            "visibility": meta["visibility"],
            "section": meta["section"],
            "project": meta.get("project") or _DEFAULT_PROJECT,
            "source_site": "noi-bo",
            "image_urls": [],
            "version": datetime.now(UTC).date().isoformat(),
        },
    )


def load_knowledge_dir(directory: Path = DEFAULT_KNOWLEDGE_DIR) -> list[LoadedDocument]:
    """Đọc toàn bộ file .md trong thư mục (đệ quy theo thư mục con)."""
    if not directory.is_dir():
        return []
    return [load_knowledge_file(path) for path in sorted(directory.rglob("*.md"))]
