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

Đúng luồng Parsing -> text thô -> Markdown: mỗi tin lấy được ghi 1 file text
thô vào data/raw/batdongsan_crawl_raw/ (gitignore, chỉ để đối chiếu/audit)
TRƯỚC khi dựng thành Markdown có heading. Ảnh (image_urls) vẫn lấy đủ như cũ.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from src.core.logging import get_logger
from src.data.contracts import LoadedDocument
from src.data.ingestion.parsers import (
    detect_property_type,
    extract_building_code,
    parse_area_m2,
    parse_price_vnd,
    sanitize_text,
)

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_TEXT_DIR = REPO_ROOT / "data" / "raw" / "batdongsan_crawl_raw"

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


def _save_raw_text(
    listing_id: str, url: str, title: str, address: str, specs: dict[str, str], description: str
) -> None:
    """Lưu text thô (trước khi dựng Markdown) — bước 'PDF/Word -> text thô'."""
    try:
        RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        specs_raw = "\n".join(f"{label}: {value}" for label, value in specs.items())
        raw = f"Nguồn: {url}\nTiêu đề: {title}\nĐịa chỉ: {address}\n{specs_raw}\nMô tả: {description}\n"
        (RAW_TEXT_DIR / f"{listing_id}.txt").write_text(raw, encoding="utf-8")
    except OSError as exc:  # không chặn crawl nếu máy hết dung lượng/quyền ghi
        logger.warning("Không lưu được text thô cho %s: %s", listing_id, exc)


def _to_markdown(title: str, address: str, specs: dict[str, str], description: str) -> str:
    """Dựng Markdown có heading rõ ràng từ dữ liệu đã trích xuất."""
    specs_block = "\n".join(f"- {label}: {value}" for label, value in specs.items())
    return (f"# {title}\n\n## Địa chỉ\n{address}\n\n## Thông số\n{specs_block}\n\n## Mô tả\n{description}").strip()


DEFAULT_PROJECT = "Vinhomes Ocean Park Gia Lâm"  # OCP1 — mặc định giữ tương thích ngược

_BEDROOM_COUNT_RE = re.compile(r"\d+")


def _extract_structured_fields(
    specs: dict[str, str], title: str, address: str, description: str
) -> dict[str, float | int | str]:
    """Rút giá/diện tích/số phòng ngủ/loại hình/mã toà để gắn vào `Chunk`
    (payload gốc trên Qdrant, dùng cho `RetrievalFilter`).

    `specs` đã tách sẵn theo nhãn rõ ràng (không phải mô tả tự do) nên dùng
    thẳng `parsers.py` — trang này không tự bịa số khi thiếu, chỉ trả những
    field rút được, thiếu thì bỏ qua thay vì đoán.
    """
    fields: dict[str, float | int | str] = {}

    price = parse_price_vnd(specs.get("Khoảng giá"))
    if price is not None:
        fields["price"] = price

    area = parse_area_m2(specs.get("Diện tích"))
    if area is not None:
        fields["area"] = area

    # "Số phòng ngủ" đã tách riêng khỏi số WC (khác chuỗi gộp "2PN, 1WC" mà
    # parse_layout() xử lý) — chỉ cần lấy số nguyên đầu tiên trong giá trị,
    # ví dụ "3 phòng" -> 3.
    bedrooms_raw = specs.get("Số phòng ngủ")
    if bedrooms_raw:
        match = _BEDROOM_COUNT_RE.search(bedrooms_raw)
        if match:
            fields["num_bedrooms"] = int(match.group())

    # CỐ Ý không quét `description` — mô tả tự do do người bán viết hay nhắc
    # loại hình LÂN CẬN chứ không phải của chính căn (vd "view sang biệt thự
    # kế bên" = view NHÌN RA biệt thự, không phải căn này là biệt thự). Người
    # bán hầu như luôn nói rõ loại hình ngay trong tiêu đề ("Bán biệt thự...",
    # "Bán căn hộ...") nên chỉ cần quét `title` là đủ tin cậy.
    property_type = detect_property_type(title)
    if property_type is not None:
        fields["property_type"] = property_type

    building = extract_building_code(f"{title} {address} {description}")
    if building is not None:
        fields["building"] = building

    return fields


def parse_listing_detail(html: str, url: str, project: str = DEFAULT_PROJECT) -> LoadedDocument | None:
    """Chuyển HTML trang chi tiết thành LoadedDocument.

    Trả None nếu trang không có tiêu đề — coi như crawl lỗi (trang bị gỡ,
    redirect sang trang khác...), bỏ qua thay vì tạo tài liệu rỗng.

    `project` gắn thẳng vào metadata — không tự suy đoán từ nội dung trang,
    vì trang lưu tay không có category chuẩn hoá như meeyland. Người gọi
    (`load_saved_detail_pages`) phải chỉ định đúng dự án theo thư mục nguồn.
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

    # Trích trước khi làm sạch — parse_price_vnd/parse_area_m2 đọc trực tiếp
    # giá trị `specs` (đã tách nhãn rõ ràng từ HTML), sanitize_text() chạy
    # sau chỉ ảnh hưởng phần TEXT hiển thị, không ảnh hưởng số đã trích.
    structured_fields = _extract_structured_fields(specs, title, address, description)

    clean_title = sanitize_text(title)
    clean_address = sanitize_text(address)
    clean_specs = {sanitize_text(k): sanitize_text(v) for k, v in specs.items()}
    clean_description = sanitize_text(description)

    listing_id = _extract_listing_id(url)
    _save_raw_text(listing_id, url, clean_title, clean_address, clean_specs, clean_description)
    text = _to_markdown(clean_title, clean_address, clean_specs, clean_description)

    return LoadedDocument(
        doc_id=f"batdongsan:{listing_id}",
        title=clean_title,
        text=text,
        source_path=url,
        metadata={
            "image_urls": image_urls,
            "visibility": "public",
            "section": project,
            "project": project,
            "source_site": "batdongsan.com.vn",
            "version": datetime.now(UTC).date().isoformat(),
            "doc_kind": "listing",
            **structured_fields,
        },
    )


_SOURCE_URL_RE = re.compile(r'<link rel="(?:canonical|alternate)"[^>]*href="(https://batdongsan\.com\.vn/[^"]+-pr\d+)"')


def _extract_source_url(html: str) -> str | None:
    """Tìm URL gốc của trang — trình duyệt vẫn giữ trong <link rel="canonical">
    dù đã lưu "Chỉ HTML", nhờ vậy trích dẫn nguồn vẫn trỏ đúng tin đăng thật.
    """
    match = _SOURCE_URL_RE.search(html)
    return match.group(1) if match else None


def load_saved_detail_pages(directory: Path, project: str = DEFAULT_PROJECT) -> list[LoadedDocument]:
    """Đọc các trang chi tiết đã lưu thủ công từ trình duyệt (Ctrl+S → "Chỉ HTML").

    Dùng khi crawl tự động bị chặn (xem docstring module) — người dùng tự
    duyệt web bình thường và lưu trang, hàm này chỉ xử lý file có sẵn trên
    máy, không gọi mạng, không né tránh gì cả.

    Không đọc đệ quy (`glob`, không `rglob`) — cố ý, để mỗi dự án nằm trong
    một thư mục riêng ("khu nào ra khu đấy") và người gọi tự chỉ đúng
    `project` khớp thư mục, thay vì đoán dự án từ nội dung trang.
    """
    html_paths = sorted(directory.glob("*.html"))
    documents: list[LoadedDocument] = []

    for path in html_paths:
        html = path.read_text(encoding="utf-8", errors="replace")
        url = _extract_source_url(html)
        if url is None:
            logger.warning("Không tìm được URL gốc trong %s — bỏ qua file này", path.name)
            continue

        document = parse_listing_detail(html, url, project)
        if document is None:
            logger.warning("Không parse được nội dung từ %s", path.name)
            continue

        documents.append(document)

    logger.info(
        "Đọc được %d/%d file HTML hợp lệ từ %s (dự án: %s)", len(documents), len(html_paths), directory, project
    )
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
