"""Crawler meeyland.com — tin đăng Vinhomes Ocean Park (OCP1/OCP2/OCP3).

Trang dùng Astro (JS-hydrate) — dữ liệu chi tiết (giá dạng số, diện tích...)
chỉ nằm trong JSON nội bộ khó parse ổn định lâu dài (tên component đổi mỗi
lần deploy). Thay vào đó lấy từ 3 phần HTML tĩnh, luôn có sẵn trong response
mà không cần chạy JS:

- <meta name="description"> — đã có sẵn câu tóm tắt diện tích/giá/mã tin
- <meta property="og:title"> — tiêu đề tin
- div.article-description — đoạn mô tả đầy đủ do người đăng viết

Trang không bị chặn bot (không có cf-mitigated: challenge như batdongsan).

Đúng luồng Parsing -> text thô -> Markdown: mỗi tin lấy được ghi 1 file text
thô vào data/raw/meeyland_crawl_raw/ (gitignore, chỉ để đối chiếu/audit)
TRƯỚC khi dựng thành Markdown có heading — không chỉ nối chuỗi phẳng như
trước. Ảnh (image_urls) vẫn lấy đủ như cũ, giữ trong metadata, không chèn
vào text (RAG chỉ cần mô tả bằng chữ).

Ba dự án — ba category khác nhau trên meeyland, "khu nào ra khu đấy":

- OCP1 (Gia Lâm): category riêng cho Vinhomes Ocean Park, không lẫn dự án
  khác — không cần lọc thêm.
- OCP2 (The Empire, Văn Giang): category riêng cho đúng dự án — không cần
  lọc thêm.
- OCP3 (The Crown, Văn Lâm): CHƯA có category "căn hộ chung cư" riêng (kiểm
  tra thật 10/08/2026: 0 tin đăng — các toà căn hộ chưa bàn giao, chưa có thị
  trường thứ cấp). Trang danh mục biệt thự/liền kề gần nhất là cấp HUYỆN
  (Văn Lâm), có thể lẫn dự án khác không phải Vinhomes — bắt buộc lọc lại
  bằng `must_mention` (kiểm tra tiêu đề/mô tả có nhắc đúng tên dự án) trước
  khi gắn nhãn project, tránh gán nhầm tin của dự án khác thành OCP3.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from src.core.logging import get_logger
from src.data.contracts import LoadedDocument

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_TEXT_DIR = REPO_ROOT / "data" / "raw" / "meeyland_crawl_raw"

BASE_URL = "https://meeyland.com"
REQUEST_DELAY_S = 1.5


@dataclass(frozen=True)
class ProjectConfig:
    """Một dự án cụ thể trên meeyland — quyết định crawl gì và gắn nhãn gì."""

    key: str  # dùng làm phần thư mục raw-text, vd "ocp2"
    project_name: str  # ghi vào metadata["project"] — PHẢI khớp tên dùng ở knowledge docs
    search_path: str  # trang danh mục (category) của đúng dự án
    must_mention: tuple[str, ...] = field(default_factory=tuple)
    """Khi khác rỗng: tiêu đề+mô tả PHẢI chứa ít nhất 1 cụm trong danh sách này
    (không phân biệt hoa/thường/dấu) thì mới nhận là thuộc dự án — bắt buộc
    với category cấp huyện (không riêng dự án) như OCP3, tránh gán nhầm tin
    của dự án/CĐT khác."""


PROJECT_OCP1 = ProjectConfig(
    key="ocp1",
    project_name="Vinhomes Ocean Park Gia Lâm",
    search_path="/ban-can-ho-chung-cu-vinhomes-ocean-park-100000004-gia-lam-ha-noi-l14422",
)

PROJECT_OCP2 = ProjectConfig(
    key="ocp2",
    project_name="Vinhomes Ocean Park 2 (The Empire)",
    search_path="/ban-can-ho-chung-cu-vinhomes-ocean-park-2-the-empire-van-giang-hung-yen-l14622",
)

PROJECT_OCP3 = ProjectConfig(
    key="ocp3",
    project_name="Vinhomes Ocean Park 3 (The Crown)",
    # Chưa có category riêng cho OCP3 (0 tin căn hộ, xem docstring) — dùng
    # category cấp huyện (biệt thự liền kề Văn Lâm) rồi lọc lại bằng must_mention.
    search_path="/ban-biet-thu-lien-ke-van-lam-hung-yen-i1422",
    must_mention=("ocean park 3", "the crown"),
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SalesMateEduBot/0.1; VinUni AI20K Cohort 3 project)",
    "Accept-Language": "vi-VN,vi;q=0.9",
}

_LISTING_LINK_RE = re.compile(r"-i\d+/\d+$")
_IMAGE_RE = re.compile(r"https://io\.meeymedia\.com/[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp)", re.IGNORECASE)
# Số điện thoại VN thật luôn 10 số liên tục bắt đầu bằng 0 — khác giá tiền
# (luôn có dấu chấm/phẩy ngăn nhóm số, vd "5.000.000.000"). Không dùng
# markup riêng để loại như batdongsan (data-kyc-name) vì mô tả ở đây là văn
# bản tự do do người đăng gõ tay, không có thẻ HTML bọc riêng số điện thoại.
_PHONE_RE = re.compile(r"\b0\d{9}\b")


@dataclass
class CrawlLimits:
    """Chặn crawl tràn lan — chỉ lấy đủ dữ liệu demo."""

    max_search_pages: int = 3
    max_listings: int | None = 40


def _text(node: Tag | None) -> str:
    return node.get_text(strip=True) if node else ""


def _extract_listing_paths(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    paths: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"].split("?")[0]
        if href.startswith("/") and _LISTING_LINK_RE.search(href) and href not in paths:
            paths.append(href)
    return paths


def _extract_listing_id(url: str) -> str:
    match = re.search(r"/(\d+)$", url)
    return match.group(1) if match else url


def _fold(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường, dùng để so khớp must_mention không phân biệt dấu/hoa-thường."""
    no_mark = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in no_mark if unicodedata.category(ch) != "Mn").lower()


def _matches_project(project: ProjectConfig, title: str, meta_desc: str, description: str) -> bool:
    """Category cấp huyện (không riêng dự án, vd OCP3) cần lọc lại bằng nội dung.

    Không có must_mention (category đã riêng cho đúng dự án) thì luôn khớp.
    """
    if not project.must_mention:
        return True
    haystack = _fold(f"{title} {meta_desc} {description}")
    return any(_fold(keyword) in haystack for keyword in project.must_mention)


def _save_raw_text(project: ProjectConfig, listing_id: str, title: str, meta_desc: str, description: str) -> None:
    """Lưu text thô (trước khi dựng Markdown) — bước 'PDF/Word -> text thô'."""
    try:
        out_dir = RAW_TEXT_DIR / project.key
        out_dir.mkdir(parents=True, exist_ok=True)
        raw = f"Nguồn: {BASE_URL}\nDự án: {project.project_name}\nTiêu đề: {title}\nMeta: {meta_desc}\nMô tả: {description}\n"
        (out_dir / f"{listing_id}.txt").write_text(raw, encoding="utf-8")
    except OSError as exc:  # không chặn crawl nếu máy hết dung lượng/quyền ghi
        logger.warning("Không lưu được text thô cho %s: %s", listing_id, exc)


def _to_markdown(title: str, meta_desc: str, description: str) -> str:
    """Dựng Markdown có heading rõ ràng từ dữ liệu đã trích xuất."""
    return (f"# {title}\n\n## Thông tin tóm tắt\n{meta_desc}\n\n## Mô tả chi tiết\n{description}").strip()


def parse_listing_detail(html: str, url: str, project: ProjectConfig = PROJECT_OCP1) -> LoadedDocument | None:
    """Chuyển HTML trang chi tiết thành LoadedDocument.

    Trả None nếu không có og:title (trang lỗi/đã gỡ) HOẶC nếu nội dung không
    nhắc đúng tên dự án theo `project.must_mention` (tránh gán nhầm tin của
    dự án/CĐT khác vào category cấp huyện dùng chung, vd OCP3).
    """
    soup = BeautifulSoup(html, "html.parser")

    title_node = soup.select_one("meta[property='og:title']")
    title = title_node.get("content", "").strip() if title_node else ""
    if not title:
        return None
    title = _PHONE_RE.sub("***", title).strip()

    meta_desc_node = soup.select_one("meta[name='description']")
    meta_desc = meta_desc_node.get("content", "").strip() if meta_desc_node else ""

    description = _PHONE_RE.sub("***", _text(soup.select_one("div.article-description p")))

    if not _matches_project(project, title, meta_desc, description):
        return None

    image_urls = sorted(set(_IMAGE_RE.findall(html)))

    listing_id = _extract_listing_id(url)
    _save_raw_text(project, listing_id, title, meta_desc, description)
    text = _to_markdown(title, meta_desc, description)

    return LoadedDocument(
        # listing_id là ID nội bộ của meeyland, đã duy nhất trên toàn site nên
        # không cần thêm project.key — giữ format cũ để tin OCP1 hiện có trên
        # Qdrant re-ingest đúng doc_id cũ (không tạo bản trùng).
        doc_id=f"meeyland:{listing_id}",
        title=title,
        text=text,
        source_path=url,
        metadata={
            "image_urls": image_urls,
            "visibility": "public",
            "section": project.project_name,
            "project": project.project_name,
            "source_site": "meeyland.com",
            "version": datetime.now(UTC).date().isoformat(),
        },
    )


async def crawl_vinhomes_ocean_park(
    limits: CrawlLimits | None = None, project: ProjectConfig = PROJECT_OCP1
) -> list[LoadedDocument]:
    """Crawl tin đăng Vinhomes Ocean Park qua category của meeyland cho đúng 1 dự án."""
    limits = limits or CrawlLimits()
    documents: list[LoadedDocument] = []

    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, follow_redirects=True, timeout=20.0) as client:
        listing_paths: list[str] = []
        for page in range(1, limits.max_search_pages + 1):
            path = project.search_path if page == 1 else f"{project.search_path}?page={page}"
            try:
                response = await client.get(path)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Không tải được trang danh sách %s: %s", path, exc)
                break

            found = _extract_listing_paths(response.text)
            if not found:
                logger.info("Trang %s không còn tin — dừng phân trang", path)
                break

            for listing_path in found:
                if listing_path not in listing_paths:
                    listing_paths.append(listing_path)
            await asyncio.sleep(REQUEST_DELAY_S)

        if limits.max_listings is not None:
            listing_paths = listing_paths[: limits.max_listings]

        logger.info("Tìm được %d tin đăng, bắt đầu lấy chi tiết", len(listing_paths))

        for listing_path in listing_paths:
            full_url = f"{BASE_URL}{listing_path}"
            try:
                response = await client.get(listing_path)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Không tải được %s: %s", full_url, exc)
                continue

            document = parse_listing_detail(response.text, full_url, project)
            if document is not None:
                documents.append(document)
            await asyncio.sleep(REQUEST_DELAY_S)

    logger.info(
        "Crawl meeyland (%s) xong: %d/%d tin lấy được nội dung (đã lọc must_mention)",
        project.project_name,
        len(documents),
        len(listing_paths),
    )
    return documents
