"""Crawler batdongsan.com.vn — tin đăng bán tại Vinhomes Ocean Park Gia Lâm.

Crawl 2 cấp: (1) trang danh sách tìm kiếm để lấy URL từng tin đăng, (2) từng
trang chi tiết để lấy nội dung. Kết quả trả về `LoadedDocument` — cắm thẳng
vào `IngestPipeline` có sẵn (`src/data/pipelines.py`), không cần thêm bước
chuyển đổi nào khác.

Tuân thủ:
- Đã kiểm tra `robots.txt` của batdongsan.com.vn (`Allow: /`, chỉ chặn vài
  endpoint nội bộ không liên quan) — đường dẫn tin đăng được phép crawl.
- Giới hạn `max_search_pages`/`max_listings` để không dội tải lên server
  nguồn — đây là crawl phục vụ demo/eval (vài chục tin), không phải thu thập
  toàn bộ site (site có tới 40+ trang kết quả).
- Nghỉ `REQUEST_DELAY_S` giữa mỗi request.
- Loại số điện thoại môi giới khỏi mô tả trước khi embed — không cần cho việc
  trả lời câu hỏi và tránh phát tán thông tin liên hệ cá nhân.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from src.core.logging import get_logger
from src.data.contracts import LoadedDocument

logger = get_logger(__name__)

BASE_URL = "https://batdongsan.com.vn"
DEFAULT_SEARCH_PATH = "/nha-dat-ban-vinhomes-ocean-park-gia-lam"

REQUEST_DELAY_S = 1.5

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SalesMateEduBot/0.1; VinUni AI20K Cohort 3 project)",
    "Accept-Language": "vi-VN,vi;q=0.9",
}

_LISTING_LINK_RE = re.compile(r"-pr\d+/?$")


@dataclass
class CrawlLimits:
    """Chặn crawl tràn lan — chỉ lấy đủ dữ liệu demo."""

    max_search_pages: int = 3
    max_listings: int | None = 40


def _text(node: Tag | None) -> str:
    return node.get_text(strip=True) if node else ""


def _extract_listing_paths(html: str) -> list[str]:
    """Lấy đường dẫn (không trùng) của từng tin đăng trên trang danh sách."""
    soup = BeautifulSoup(html, "html.parser")
    paths: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"].split("?")[0].split("#")[0]
        if href.startswith("/") and _LISTING_LINK_RE.search(href) and href not in paths:
            paths.append(href)
    return paths


def _extract_listing_id(path: str) -> str:
    match = re.search(r"-pr(\d+)/?$", path)
    return match.group(1) if match else path


def parse_listing_detail(html: str, url: str) -> LoadedDocument | None:
    """Chuyển HTML trang chi tiết thành LoadedDocument.

    Trả None nếu trang không có tiêu đề — coi như crawl lỗi (trang bị gỡ,
    redirect sang trang khác...), bỏ qua thay vì tạo tài liệu rỗng.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = _text(soup.select_one("h1.re__pr-title"))
    if not title:
        return None

    address = ", ".join(
        line for line in (_text(node) for node in soup.select(".re__address-line-1, .re__address-line-2")) if line
    )

    specs: dict[str, str] = {}
    for item in soup.select(".re__pr-specs-content-item"):
        label = _text(item.select_one(".re__pr-specs-content-item-title"))
        value = _text(item.select_one(".re__pr-specs-content-item-value"))
        if label and value:
            specs[label] = value

    description_node = soup.select_one(".re__detail-content.js__pr-description")
    if description_node is not None:
        for phone_span in description_node.select("span[data-kyc-name]"):
            phone_span.decompose()
        description = description_node.get_text("\n", strip=True)
    else:
        description = ""

    # Ảnh dùng lazyload: ảnh đầu có "src", ảnh sau chỉ có "data-src". Chỉ lấy
    # URL — không tải file ảnh về, widget hiển thị bằng cách trỏ thẳng URL này.
    image_urls: list[str] = []
    for img in soup.select("img.pr-img"):
        src = img.get("data-src") or img.get("src")
        if src and src not in image_urls:
            image_urls.append(src)

    specs_block = "\n".join(f"- {label}: {value}" for label, value in specs.items())
    text = f"{title}\nĐịa chỉ: {address}\n{specs_block}\n\nMô tả:\n{description}".strip()

    listing_id = _extract_listing_id(url)
    return LoadedDocument(
        doc_id=f"batdongsan:{listing_id}",
        title=title,
        text=text,
        source_path=url,
        metadata={
            "image_urls": image_urls,
            "visibility": "public",
            "section": "Vinhomes Ocean Park Gia Lâm",
            "source_site": "batdongsan.com.vn",
        },
    )


_SOURCE_URL_RE = re.compile(r'<link rel="(?:canonical|alternate)"[^>]*href="(https://batdongsan\.com\.vn/[^"]+-pr\d+)"')


def _extract_source_url(html: str) -> str | None:
    """Tìm URL gốc của trang — trình duyệt vẫn giữ trong <link rel="canonical">
    dù đã lưu "Chỉ HTML", nhờ vậy trích dẫn nguồn vẫn trỏ đúng tin đăng thật.
    """
    match = _SOURCE_URL_RE.search(html)
    return match.group(1) if match else None


def load_saved_detail_pages(directory: Path) -> list[LoadedDocument]:
    """Đọc các trang chi tiết đã lưu thủ công từ trình duyệt (Ctrl+S → "Chỉ HTML").

    Dùng khi crawl tự động bị chặn (xem docstring module) — người dùng tự
    duyệt web bình thường và lưu trang, hàm này chỉ xử lý file có sẵn trên
    máy, không gọi mạng, không né tránh gì cả.
    """
    html_paths = sorted(directory.glob("*.html"))
    documents: list[LoadedDocument] = []

    for path in html_paths:
        html = path.read_text(encoding="utf-8", errors="replace")
        url = _extract_source_url(html)
        if url is None:
            logger.warning("Không tìm được URL gốc trong %s — bỏ qua file này", path.name)
            continue

        document = parse_listing_detail(html, url)
        if document is None:
            logger.warning("Không parse được nội dung từ %s", path.name)
            continue

        documents.append(document)

    logger.info("Đọc được %d/%d file HTML hợp lệ từ %s", len(documents), len(html_paths), directory)
    return documents


async def crawl_vinhomes_ocean_park(
    limits: CrawlLimits | None = None,
    search_path: str = DEFAULT_SEARCH_PATH,
) -> list[LoadedDocument]:
    """Crawl tin đăng bán tại Vinhomes Ocean Park Gia Lâm.

    Một tin lỗi (parse hỏng, HTTP lỗi) chỉ bị bỏ qua và ghi log — không làm
    hỏng cả lượt crawl.
    """
    limits = limits or CrawlLimits()
    documents: list[LoadedDocument] = []

    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, follow_redirects=True, timeout=20.0) as client:
        listing_paths: list[str] = []
        for page in range(1, limits.max_search_pages + 1):
            path = search_path if page == 1 else f"{search_path}/p{page}"
            try:
                response = await client.get(path)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Không tải được trang danh sách %s: %s", path, exc)
                break

            found = _extract_listing_paths(response.text)
            if not found:
                logger.info("Trang %s không còn tin đăng nào — dừng phân trang", path)
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
                logger.warning("Không tải được tin đăng %s: %s", full_url, exc)
                continue

            document = parse_listing_detail(response.text, full_url)
            if document is None:
                logger.warning("Không parse được tin đăng %s", full_url)
                continue

            documents.append(document)
            await asyncio.sleep(REQUEST_DELAY_S)

    logger.info("Crawl xong: %d/%d tin đăng lấy được nội dung", len(documents), len(listing_paths))
    return documents
