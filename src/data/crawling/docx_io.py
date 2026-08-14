"""Ghi và đọc `.docx` — chốt kiểm soát nội dung giữa crawl và nạp dữ liệu.

Vì sao chèn Word vào giữa: crawl xong KHÔNG nạp thẳng. Người phụ trách dữ liệu
mở `.docx` đọc, sửa, xoá phần rác, rồi mới cho nạp. Nội dung sai mà lọt vào
Qdrant thì trợ lý sẽ nói sai với khách, và không ai biết cho tới lúc khách hỏi.

    crawl → data/raw/crawled/*.docx   ← người duyệt ở đây
                  ↓
            data/raw/knowledge/*.md   ← có front-matter, sẵn sàng nạp

Front-matter sinh tự động từ Excel; người duyệt sửa thẳng trong `.docx` phần
nội dung, không phải gõ lại metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt

from src.core.logging import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
THU_MUC_DOCX = REPO_ROOT / "data" / "raw" / "crawled"
THU_MUC_MD = REPO_ROOT / "data" / "raw" / "knowledge"

# Ký tự Windows không cho phép trong tên file.
_KY_TU_CAM = '<>:"/\\|?*'


def ten_file_an_toan(ten: str) -> str:
    """Giữ nguyên tên tiếng Việt, chỉ bỏ ký tự hệ thống không cho phép."""
    sach = "".join("-" if c in _KY_TU_CAM else c for c in ten)
    return " ".join(sach.split()).strip(". ")


def ghi_docx(
    *,
    tieu_de: str,
    noi_dung: str,
    url: str,
    khu_vuc: str,
    thieu: list[str],
    thu_muc: Path = THU_MUC_DOCX,
) -> Path:
    """Ghi một tài liệu ra `.docx` để người dùng duyệt."""
    thu_muc.mkdir(parents=True, exist_ok=True)
    doc = Document()

    doc.add_heading(tieu_de, level=1)

    # Khối nguồn: người duyệt cần biết nội dung này lấy từ đâu để đối chiếu.
    meta = doc.add_paragraph()
    meta.add_run("Nguồn: ").bold = True
    meta.add_run(url)
    if khu_vuc:
        p = doc.add_paragraph()
        p.add_run("Khu vực: ").bold = True
        p.add_run(khu_vuc)

    if thieu:
        canh_bao = doc.add_paragraph()
        run = canh_bao.add_run(f"⚠ Chưa lấy được: {', '.join(thieu)}")
        run.bold = True
        run.font.size = Pt(10)

    doc.add_paragraph("")
    for dong in noi_dung.split("\n"):
        dong = dong.rstrip()
        if not dong:
            continue
        if dong.startswith("## "):
            doc.add_heading(dong[3:].strip(), level=2)
        elif dong.startswith("- "):
            doc.add_paragraph(dong[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(dong)

    path = thu_muc / f"{ten_file_an_toan(tieu_de)}.docx"
    doc.save(path)
    logger.info("Đã ghi %s", path.name)
    return path


def _doc_docx(path: Path) -> tuple[str, str, str, list[str]]:
    """Đọc lại `.docx` → (tiêu đề, nội dung markdown, url, khu vực)."""
    doc = Document(path)
    tieu_de, url, khu_vuc = "", "", ""
    dong: list[str] = []

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower()

        if style.startswith("heading 1") and not tieu_de:
            tieu_de = text
        elif text.startswith("Nguồn:"):
            url = text.removeprefix("Nguồn:").strip()
        elif text.startswith("Khu vực:"):
            khu_vuc = text.removeprefix("Khu vực:").strip()
        elif text.startswith("⚠"):
            continue  # ghi chú cho người duyệt, không phải nội dung
        elif style.startswith("heading"):
            # Nhiều trang đặt tên mục trùng tên bài ("Vị trí Vinhomes Ocean
            # Park 2" là cả tiêu đề lẫn tên mục). Giữ cả hai chỉ tổ lặp.
            if text.casefold() != tieu_de.casefold():
                dong.append(f"## {text}")
        elif style.startswith("list"):
            dong.append(f"- {text}")
        else:
            dong.append(text)

    return tieu_de or path.stem, "\n\n".join(dong), url, khu_vuc


def docx_sang_md(
    path: Path,
    *,
    section: str = "",
    thu_muc: Path = THU_MUC_MD,
    ngay: str | None = None,
) -> Path:
    """Đổi một `.docx` đã duyệt thành `.md` kèm front-matter đủ khoá bắt buộc."""
    tieu_de, noi_dung, url, khu_vuc = _doc_docx(path)
    thu_muc.mkdir(parents=True, exist_ok=True)

    domain = url.split("/")[2] if "://" in url else "noi-bo"
    front = [
        "---",
        f"title: {tieu_de}",
        f"section: {section or tieu_de}",
        # project rỗng khi tài liệu không thuộc dự án cụ thể (chính sách chung).
        f"project: {khu_vuc or 'Vinhomes Ocean Park'}",
        f"source_site: {domain}",
        f"source_url: {url}",
        "visibility: public",
        # Bắt buộc: bộ truy hồi lọc theo khoá này để câu hỏi chính sách không
        # bị 800+ tin rao vặt lấn át. Thiếu nó là tài liệu vô hình.
        "doc_kind: policy",
        "image_urls: []",
        f"version: {ngay or datetime.now(UTC).date().isoformat()}",
        "---",
        "",
        # Không lặp lại tiêu đề ở thân bài: front-matter đã khai `title`, và
        # pipeline tự ghép tiêu đề vào văn bản đem nhúng. Ghi thêm ở đây thì
        # chunk đầu của mọi tài liệu mở màn bằng tiêu đề lặp mấy lượt.
        noi_dung,
        "",
    ]

    out = thu_muc / f"{ten_file_an_toan(tieu_de)}.md"
    out.write_text("\n".join(front), encoding="utf-8")
    logger.info("Đã ghi %s", out.name)
    return out
