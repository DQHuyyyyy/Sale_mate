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
from src.data.ingestion.parsers import detect_property_type, extract_building_code, parse_layout, sanitize_text

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_TEXT_DIR = REPO_ROOT / "data" / "raw" / "meeyland_crawl_raw"

BASE_URL = "https://meeyland.com"
REQUEST_DELAY_S = 1.5

# CỐ Ý không có "masterise": xác minh thật thấy Masterise Homes cũng là đơn vị
# xây một số phân khu CHÍNH THỨC bên trong OCP1 (vd "Lumiere Orient Pearl" tự
# nhận rõ "tại Ocean Park 1"/"OCP1" dù do Masterise xây) — loại theo tên này
# sẽ xoá oan tin thật. "MIK Group"/"Imperia" ("The Parkland") thì khác: tin
# xác nhận là dự án riêng, gắn nhãn "Ocean City" chung chung, KHÔNG tự nhận
# thuộc Ocean Park 1/2/3 nào — loại được an toàn hơn.
_OTHER_DEVELOPERS: tuple[str, ...] = ("mik group", "imperia")


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
    exclude_mentions: tuple[str, ...] = field(default_factory=lambda: _OTHER_DEVELOPERS)
    """Tên CĐT KHÁC — có thì loại NGAY dù category tưởng là "riêng" cho dự án
    này. Phát hiện thật 10/08/2026: category "Vinhomes Ocean Park 2" trên
    meeyland lẫn cả tin của Masterise Homes ("Lumière Ocean Crest") và MIK
    Group/Imperia ("The Parkland") — 2 dự án khác, cùng nằm trong vùng
    "Ocean City" rộng nhưng KHÔNG phải Vinhomes. Đáng lưu ý: KHÔNG dùng riêng
    từ "Lumiere"/"Lumière" để loại — Vinhomes tự đặt tên vài toà của chính họ
    trùng chữ này (vd "Lumiere Orient Pearl" ở OCP1, "Lumiere SpringBay" ở
    OCP2, cả hai đã tự xác nhận rõ "(Vinhomes Ocean Park ...)" trong mô tả) —
    loại theo "Lumiere" sẽ xoá oan tin thật. Phải loại theo TÊN CĐT tường minh."""


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

# meta_desc tự sinh của meeyland luôn có dạng cố định:
# "... Diện tích 64m², giá 4.200.000.000  VNĐ. Mã tin rao: ..." — số đã ở đơn
# vị đồng đầy đủ (không phải dạng "X tỷ"/"X triệu" như parsers.parse_price_vnd
# xử lý), nên tách riêng bằng 2 regex khớp đúng khuôn này thay vì dùng chung.
_AREA_META_RE = re.compile(r"Diện tích\s*([\d.,]+)\s*m²")
_PRICE_META_RE = re.compile(r"giá\s*([\d.]+)\s*VNĐ", re.IGNORECASE)


def _extract_structured_fields(meta_desc: str, title: str, description: str) -> dict[str, float | int | str]:
    """Rút giá/diện tích/số phòng ngủ/loại hình/mã toà từ tin đăng để gắn vào
    `Chunk` (payload gốc trên Qdrant, dùng cho `RetrievalFilter`).

    Không suy đoán khi thiếu — field nào rút được thì gắn, rút không được thì
    bỏ qua, tuyệt đối không gán giá trị đoán hay mặc định.
    """
    fields: dict[str, float | int | str] = {}

    area_match = _AREA_META_RE.search(meta_desc)
    if area_match:
        fields["area"] = float(area_match.group(1).replace(",", "."))

    price_match = _PRICE_META_RE.search(meta_desc)
    if price_match:
        # Số đã ở đơn vị đồng, chỉ có dấu chấm ngăn nhóm nghìn — bỏ dấu chấm rồi ép int.
        fields["price"] = int(price_match.group(1).replace(".", ""))

    # meta_desc không có số phòng ngủ — thử tiêu đề (thường ghi "2PN", "3 PN"...).
    # parse_layout() trả (0, 1) cho "Studio", nên chỉ gắn khi rút được số thật.
    bedrooms, _bathrooms = parse_layout(title)
    if bedrooms is not None:
        fields["num_bedrooms"] = bedrooms

    # CỐ Ý không quét `description` — mô tả tự do do người bán viết hay nhắc
    # loại hình LÂN CẬN chứ không phải của chính căn (vd "view hồ và biệt thự"
    # = view NHÌN RA biệt thự, không phải căn này là biệt thự). `meta_desc` là
    # mô tả TỰ SINH của meeyland theo đúng category tin đăng (luôn ghi "căn hộ
    # chung cư" hoặc "biệt thự liền kề"...) nên đáng tin hơn nhiều.
    property_type = detect_property_type(f"{title} {meta_desc}")
    if property_type is not None:
        fields["property_type"] = property_type

    # building thì vẫn quét description — yêu cầu đúng cụm "tòa <mã>" nên rủi
    # ro bắt nhầm thấp hơn hẳn so với property_type quét từ khoá đơn lẻ.
    building = extract_building_code(f"{title} {description}")
    if building is not None:
        fields["building"] = building

    return fields


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
    """Lọc đúng dự án — kiểm tra exclude_mentions TRƯỚC must_mention.

    exclude_mentions luôn được kiểm tra dù category "tưởng riêng" cho dự án
    (must_mention rỗng) — meta_desc do meeyland tự sinh theo category nên
    LUÔN nhắc đúng tên dự án dù tin thật của CĐT khác (xem docstring
    ProjectConfig), phải đọc `description` (do người bán tự viết) mới phát
    hiện được CĐT thật.
    """
    haystack = _fold(f"{title} {meta_desc} {description}")
    if any(_fold(keyword) in haystack for keyword in project.exclude_mentions):
        return False
    if not project.must_mention:
        return True
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

    # Trích price/area/num_bedrooms/property_type/building TRƯỚC khi làm sạch
    # — _extract_structured_fields() đọc đúng khuôn "Diện tích Xm², giá Y VNĐ"
    # tự sinh của meeyland trên meta_desc GỐC; sanitize_text() phía dưới XOÁ
    # cụm quảng cáo/SĐT nên chạy sau mới không ảnh hưởng tới việc trích số.
    structured_fields = _extract_structured_fields(meta_desc, title, description)

    # Làm sạch (SĐT còn sót có nhãn dẫn, cụm quảng cáo, HTML entity, unicode
    # ẩn) cho phần TEXT cuối cùng đưa vào RAG — giữ nguyên xuống dòng vì
    # _to_markdown() dựng heading `##` dựa trên các biến này.
    clean_title = sanitize_text(title)
    clean_meta_desc = sanitize_text(meta_desc)
    clean_description = sanitize_text(description)

    image_urls = sorted(set(_IMAGE_RE.findall(html)))

    listing_id = _extract_listing_id(url)
    _save_raw_text(project, listing_id, clean_title, clean_meta_desc, clean_description)
    text = _to_markdown(clean_title, clean_meta_desc, clean_description)

    return LoadedDocument(
        # listing_id là ID nội bộ của meeyland, đã duy nhất trên toàn site nên
        # không cần thêm project.key — giữ format cũ để tin OCP1 hiện có trên
        # Qdrant re-ingest đúng doc_id cũ (không tạo bản trùng).
        doc_id=f"meeyland:{listing_id}",
        title=clean_title,
        text=text,
        source_path=url,
        metadata={
            "image_urls": image_urls,
            "visibility": "public",
            "section": project.project_name,
            "project": project.project_name,
            "source_site": "meeyland.com",
            # Tin rao — tách khỏi tài liệu chính sách để truy hồi lọc được.
            "doc_kind": "listing",
            "version": datetime.now(UTC).date().isoformat(),
            "doc_kind": "listing",
            **structured_fields,
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
