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

    Raise ValueError nếu thiếu/sai front-matter — thà báo lỗi sớm còn hơn
    ingest một tài liệu gắn nhầm quyền truy cập.
    """
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw, path.name)

    return LoadedDocument(
        doc_id=f"knowledge:{path.stem}",
        title=meta["title"],
        # KHÔNG chèn tiêu đề vào text. Ngữ cảnh tài liệu do `_van_ban_nhung()`
        # trong pipeline ghép vào lúc nhúng, và chỉ lúc nhúng — `chunk.text` giữ
        # nội dung thuần để trích dẫn hiện ra không lặp tiêu đề.
        text=body,
        source_path=str(path),
        # Đọc TỪ front-matter, chỉ rơi về mặc định khi file không khai. Trước
        # đây `project`/`source_site`/`version` ghi cứng ở đây, nên mọi giá trị
        # khai trong file đều bị bỏ — kể cả `doc_kind`, khoá mà truy hồi dùng
        # để lọc. Tài liệu ghi đúng vẫn bị coi như không có nhãn.
        metadata={
            "visibility": meta["visibility"],
            "section": meta["section"],
            "project": meta.get("project") or "Vinhomes Ocean Park Gia Lâm",
            "source_site": meta.get("source_site") or "noi-bo",
            "source_url": meta.get("source_url", ""),
            "doc_kind": meta.get("doc_kind") or "policy",
            "image_urls": [],
            "version": meta.get("version") or datetime.now(UTC).date().isoformat(),
        },
    )


def load_knowledge_dir(directory: Path = DEFAULT_KNOWLEDGE_DIR) -> list[LoadedDocument]:
    """Đọc toàn bộ file .md trong thư mục (đệ quy theo thư mục con)."""
    if not directory.is_dir():
        return []
    return [load_knowledge_file(path) for path in sorted(directory.rglob("*.md"))]
