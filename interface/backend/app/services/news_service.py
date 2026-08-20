"""Dịch vụ lấy tin tức thị trường bất động sản mới nhất từ nhiều nguồn báo uy tín qua RSS.

Hỗ trợ các nguồn: VnExpress, CafeF, Dân Trí, VietnamNet, VTC News, Tuổi Trẻ.
Chạy bất đồng bộ (asyncio) song song mọi nguồn, đan xen bài viết đều giữa các nguồn và lưu cache.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Danh sách nguồn RSS chuyên mục Bất động sản đa dạng
NEWS_SOURCES = [
    {
        "source": "VnExpress",
        "name": "VnExpress Bất động sản",
        "url": "https://vnexpress.net/rss/bat-dong-san.rss",
    },
    {
        "source": "CafeF",
        "name": "CafeF Bất động sản",
        "url": "https://cafef.vn/bat-dong-san.rss",
    },
    {
        "source": "Dân Trí",
        "name": "Dân Trí Bất động sản",
        "url": "https://dantri.com.vn/rss/bat-dong-san.rss",
    },
    {
        "source": "VietnamNet",
        "name": "VietnamNet Bất động sản",
        "url": "https://vietnamnet.vn/rss/bat-dong-san.rss",
    },
    {
        "source": "VTC News",
        "name": "VTC News Bất động sản",
        "url": "https://vtcnews.vn/rss/bat-dong-san.rss",
    },
    {
        "source": "Tuổi Trẻ",
        "name": "Tuổi Trẻ Kinh doanh - BĐS",
        "url": "https://tuoitre.vn/rss/kinh-doanh.rss",
    },
]

# Dữ liệu dự phòng khi toàn bộ mạng lỗi
FALLBACK_NEWS: list[dict[str, Any]] = [
    {
        "id": "fb-1",
        "title": "Thị trường bất động sản phía Đông Hà Nội sôi động nhờ hạ tầng kết nối",
        "link": "https://vnexpress.net/bat-dong-san",
        "image_url": "/media/ocean-park-tong-quan.jpg",
        "source": "VnExpress",
        "source_name": "VnExpress Bất động sản",
        "pub_date": "Hôm nay",
        "summary": "Hạ tầng giao thông đồng bộ cùng các đại đô thị biển hồ tạo sức hút mạnh mẽ cho thị trường bất động sản khu vực phía Đông Thủ đô.",
    },
    {
        "id": "fb-2",
        "title": "Xu hướng tìm kiếm căn hộ tiện ích khép kín gia tăng mạnh trong năm 2026",
        "link": "https://cafef.vn/bat-dong-san.chn",
        "image_url": "/media/ocean-park-1.jpg",
        "source": "CafeF",
        "source_name": "CafeF Bất động sản",
        "pub_date": "Hôm nay",
        "summary": "Người mua nhà ngày càng ưu tiên các dự án có hệ sinh thái tiện ích 'tất cả trong một' gồm trường học, y tế, công viên và khu thương mại.",
    },
    {
        "id": "fb-3",
        "title": "Nguồn cung căn hộ phân khúc cao cấp dẫn dắt dòng tiền đầu tư",
        "link": "https://dantri.com.vn/bat-dong-san.htm",
        "image_url": "/media/ocean-park-2.jpg",
        "source": "Dân Trí",
        "source_name": "Dân Trí Bất động sản",
        "pub_date": "Hôm nay",
        "summary": "Nhiều dự án hoàn thiện pháp lý và bàn giao đúng cam kết tiếp tục thu hút người có nhu cầu ở thực lẫn nhà đầu tư dài hạn.",
    },
    {
        "id": "fb-4",
        "title": "Tiến độ các tuyến vành đai thúc đẩy giá trị bất động sản đô thị vệ tinh",
        "link": "https://vietnamnet.vn/bat-dong-san",
        "image_url": "/media/ocean-park-3.jpg",
        "source": "VietnamNet",
        "source_name": "VietnamNet Bất động sản",
        "pub_date": "Hôm nay",
        "summary": "Các tuyến đường Vành đai 3.5 và Vành đai 4 mở rộng không gian phát triển, kết nối thuận tiện giữa các trung tâm kinh tế và khu đô thị mới.",
    },
]

# In-memory cache
_CACHE_DATA: list[dict[str, Any]] = []
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 10 * 60  # Cache 10 phút


def _extract_image(item: ET.Element, desc: str) -> str:
    """Trích xuất link ảnh đại diện từ enclosure hoặc nội dung description."""
    enclosure = item.find("enclosure")
    if enclosure is not None and enclosure.get("url"):
        return enclosure.get("url", "").strip()

    for child in item:
        if child.tag.endswith("content") and child.get("url"):
            return child.get("url", "").strip()

    if desc:
        match = re.search(r'src=[\'"]([^\'"]+)[\'"]', desc, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def _clean_summary(desc: str) -> str:
    """Làm sạch HTML tags trong thẻ description để lấy đoạn tóm tắt ngắn."""
    if not desc:
        return ""
    clean = re.sub(r"<[^>]+>", "", desc)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


async def _fetch_single_source(source_info: dict[str, str], client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Tải và parse RSS của một nguồn báo bất đồng bộ."""
    articles: list[dict[str, Any]] = []
    try:
        resp = await client.get(
            source_info["url"],
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
            timeout=5.0,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.warning("Nguồn %s trả về mã lỗi HTTP %d", source_info["name"], resp.status_code)
            return articles

        root = ET.fromstring(resp.content)
        for idx, item in enumerate(root.findall(".//item")):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = item.findtext("description") or ""

            if not title or not link:
                continue

            image_url = _extract_image(item, desc)
            summary = _clean_summary(desc)

            articles.append({
                "id": f"{source_info['source'].lower()}-{idx}-{abs(hash(link)) & 0xfffffff}",
                "title": title,
                "link": link,
                "image_url": image_url,
                "source": source_info["source"],
                "source_name": source_info["name"],
                "pub_date": pub_date,
                "summary": summary,
            })
    except Exception as exc:
        logger.warning("Không thể tải tin từ %s: %s", source_info["name"], exc)

    return articles


def _interleave_articles(lists_of_articles: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Đan xen lần lượt các bài viết từ từng nguồn để kết quả phong phú, đa dạng."""
    combined: list[dict[str, Any]] = []
    max_len = max((len(lst) for lst in lists_of_articles), default=0)
    for i in range(max_len):
        for lst in lists_of_articles:
            if i < len(lst):
                combined.append(lst[i])
    return combined


async def get_real_estate_news_async(limit: int = 10, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Lấy danh sách tin tức bất động sản mới nhất từ nhiều nguồn đa dạng (bất đồng bộ)."""
    global _CACHE_DATA, _CACHE_TIMESTAMP

    now = time.time()
    if not force_refresh and _CACHE_DATA and (now - _CACHE_TIMESTAMP < _CACHE_TTL_SECONDS):
        return _CACHE_DATA[:limit]

    try:
        async with httpx.AsyncClient() as client:
            tasks = [_fetch_single_source(src, client) for src in NEWS_SOURCES]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_lists: list[list[dict[str, Any]]] = []
        for res in results:
            if isinstance(res, list) and res:
                valid_lists.append(res)

        if valid_lists:
            interleaved = _interleave_articles(valid_lists)
            _CACHE_DATA = interleaved
            _CACHE_TIMESTAMP = now
            logger.info("Đã cập nhật %d tin tức bất động sản đa nguồn", len(interleaved))
            return _CACHE_DATA[:limit]
    except Exception as exc:
        logger.warning("Lỗi khi tải tin tức bất động sản: %s", exc)

    if _CACHE_DATA:
        return _CACHE_DATA[:limit]

    return FALLBACK_NEWS[:limit]
