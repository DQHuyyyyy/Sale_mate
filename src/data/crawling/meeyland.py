"""Crawler meeyland.com — tin đăng Vinhomes Ocean Park Gia Lâm.

Trang dùng Astro (JS-hydrate) — dữ liệu chi tiết (giá dạng số, diện tích...)
chỉ nằm trong JSON nội bộ khó parse ổn định lâu dài (tên component đổi mỗi
lần deploy). Thay vào đó lấy từ 3 phần HTML tĩnh, luôn có sẵn trong response
mà không cần chạy JS:

- <meta name="description"> — đã có sẵn câu tóm tắt diện tích/giá/mã tin
- <meta property="og:title"> — tiêu đề tin
- div.article-description — đoạn mô tả đầy đủ do người đăng viết

Trang không bị chặn bot (không có cf-mitigated: challenge như batdongsan).
Có category riêng cho Vinhomes Ocean Park nên không cần lọc từ khoá thủ công.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup, Tag

from src.core.logging import get_logger
from src.data.contracts import LoadedDocument

logger = get_logger(__name__)

BASE_URL = "https://meeyland.com"
SEARCH_PATH = "/ban-can-ho-chung-cu-vinhomes-ocean-park-100000004-gia-lam-ha-noi-l14422"

REQUEST_DELAY_S = 1.5

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


def parse_listing_detail(html: str, url: str) -> LoadedDocument | None:
    """Chuyển HTML trang chi tiết thành LoadedDocument.

    Trả None nếu không có og:title — coi như trang lỗi/đã gỡ.
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

    image_urls = sorted(set(_IMAGE_RE.findall(html)))

    listing_id = _extract_listing_id(url)
    text = f"{title}\n{meta_desc}\n\nMô tả:\n{description}".strip()

    return LoadedDocument(
        doc_id=f"meeyland:{listing_id}",
        title=title,
        text=text,
        source_path=url,
        metadata={
            "image_urls": image_urls,
            "visibility": "public",
            "section": "Vinhomes Ocean Park Gia Lâm",
            "project": "Vinhomes Ocean Park Gia Lâm",
            "source_site": "meeyland.com",
            "version": datetime.now(UTC).date().isoformat(),
        },
    )


async def crawl_vinhomes_ocean_park(limits: CrawlLimits | None = None) -> list[LoadedDocument]:
    """Crawl tin đăng Vinhomes Ocean Park qua category riêng của meeyland."""
    limits = limits or CrawlLimits()
    documents: list[LoadedDocument] = []

    async with httpx.AsyncClient(base_url=BASE_URL, headers=_HEADERS, follow_redirects=True, timeout=20.0) as client:
        listing_paths: list[str] = []
        for page in range(1, limits.max_search_pages + 1):
            path = SEARCH_PATH if page == 1 else f"{SEARCH_PATH}?page={page}"
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

            document = parse_listing_detail(response.text, full_url)
            if document is not None:
                documents.append(document)
            await asyncio.sleep(REQUEST_DELAY_S)

    logger.info("Crawl meeyland xong: %d/%d tin lấy được nội dung", len(documents), len(listing_paths))
    return documents
