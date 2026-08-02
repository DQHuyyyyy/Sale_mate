"""Nguồn dữ liệu cho trang portal (tin đăng, dự án, nhu cầu, thống kê).

Repository pattern: FE gọi API thật ngay từ ngày đầu; hôm nay dữ liệu nằm trong
bộ nhớ, mai đổi sang SQL chỉ cần thêm SqlPortalRepository và sửa src/bootstrap.py.
Bên gọi (router) không đổi một dòng.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from src.models.portal import (
    Demand,
    Listing,
    ListingType,
    MarketBar,
    MarketStats,
    Project,
    PropertyKind,
)


@runtime_checkable
class PortalRepository(Protocol):
    """Hợp đồng đọc dữ liệu portal."""

    async def list_listings(self, *, listing_type: ListingType | None = None, limit: int = 20) -> list[Listing]: ...

    async def list_projects(self, *, limit: int = 20) -> list[Project]: ...

    async def list_demands(self, *, limit: int = 20) -> list[Demand]: ...

    async def market_stats(self) -> MarketStats: ...


_LISTINGS: list[Listing] = [
    Listing(
        id="ls-001",
        title="Bán căn hộ 2PN Lakeside Metropole, view hồ",
        listing_type=ListingType.SALE,
        kind=PropertyKind.APARTMENT,
        price_label="3,85 tỷ",
        unit_price_label="56 tr/m²",
        area_label="68 m²",
        bedrooms_label="2 PN",
        location="Tây Hồ, Hà Nội",
        is_verified=True,
        photo_count=12,
    ),
    Listing(
        id="ls-002",
        title="Nhà phố 5 tầng khu đô thị, sổ đỏ chính chủ",
        listing_type=ListingType.SALE,
        kind=PropertyKind.HOUSE,
        price_label="6,5 tỷ",
        unit_price_label="92 tr/m²",
        area_label="70 m²",
        bedrooms_label="4 PN",
        location="Cầu Giấy, Hà Nội",
        is_verified=True,
        photo_count=18,
    ),
    Listing(
        id="ls-003",
        title="Căn hộ 3PN The Origin Riverside, full nội thất",
        listing_type=ListingType.SALE,
        kind=PropertyKind.APARTMENT,
        price_label="4,2 tỷ",
        unit_price_label="48 tr/m²",
        area_label="88 m²",
        bedrooms_label="3 PN",
        location="Thủ Đức, HCM",
        is_verified=True,
        photo_count=9,
    ),
    Listing(
        id="ls-004",
        title="Đất nền dự án Sunrise Garden City, giá gốc CĐT",
        listing_type=ListingType.SALE,
        kind=PropertyKind.LAND,
        price_label="2,1 tỷ",
        unit_price_label="35 tr/m²",
        area_label="60 m²",
        bedrooms_label="—",
        location="Long Biên, Hà Nội",
        is_verified=False,
        photo_count=6,
    ),
    Listing(
        id="ls-005",
        title="Cho thuê căn hộ 2PN full nội thất, gần trung tâm",
        listing_type=ListingType.RENT,
        kind=PropertyKind.APARTMENT,
        price_label="14 triệu/tháng",
        unit_price_label="",
        area_label="72 m²",
        bedrooms_label="2 PN",
        location="Ba Đình, Hà Nội",
        is_verified=True,
        photo_count=11,
    ),
    Listing(
        id="ls-006",
        title="Cho thuê shophouse mặt tiền, phù hợp kinh doanh",
        listing_type=ListingType.RENT,
        kind=PropertyKind.SHOPHOUSE,
        price_label="45 triệu/tháng",
        unit_price_label="",
        area_label="114 m²",
        bedrooms_label="—",
        location="Nam Từ Liêm, Hà Nội",
        is_verified=False,
        photo_count=8,
    ),
    Listing(
        id="ls-007",
        title="Sang nhượng quán cà phê đang hoạt động, khách ổn định",
        listing_type=ListingType.TRANSFER,
        kind=PropertyKind.SHOPHOUSE,
        price_label="380 triệu",
        unit_price_label="",
        area_label="55 m²",
        bedrooms_label="—",
        location="Hai Bà Trưng, Hà Nội",
        is_verified=False,
        photo_count=14,
    ),
    Listing(
        id="ls-008",
        title="Sang nhượng mặt bằng tầng 1 toà văn phòng",
        listing_type=ListingType.TRANSFER,
        kind=PropertyKind.SHOPHOUSE,
        price_label="620 triệu",
        unit_price_label="",
        area_label="90 m²",
        bedrooms_label="—",
        location="Thanh Xuân, Hà Nội",
        is_verified=True,
        photo_count=7,
    ),
]

_PROJECTS: list[Project] = [
    Project(
        id="pj-001",
        name="Lakeside Metropole",
        developer="CĐT An Phú",
        location="Tây Hồ, Hà Nội",
        price_from_label="3,2 tỷ",
    ),
    Project(
        id="pj-002",
        name="The Origin Riverside",
        developer="CĐT Nam Long",
        location="Thủ Đức, HCM",
        price_from_label="2,8 tỷ",
    ),
    Project(
        id="pj-003",
        name="Sunrise Garden City",
        developer="CĐT Hoàng Gia",
        location="Long Biên, Hà Nội",
        price_from_label="2,1 tỷ",
    ),
]

_DEMANDS: list[Demand] = [
    Demand(
        id="dm-001",
        author_name="Tuấn Anh",
        author_initials="TA",
        posted_label="2 giờ trước",
        summary="Vốn 420 triệu, tìm đất nền cửa ngõ khu vực phía Tây Hà Nội.",
    ),
    Demand(
        id="dm-002",
        author_name="Mỹ Linh",
        author_initials="ML",
        posted_label="3 giờ trước",
        summary="Vốn 400 triệu sở hữu đất nền sổ đỏ, ưu tiên pháp lý rõ ràng.",
    ),
    Demand(
        id="dm-003",
        author_name="Quốc Huy",
        author_initials="QH",
        posted_label="5 giờ trước",
        summary="Cần mua shophouse 6×19m, tầm giá 1,6 tỷ và 5 triệu/tháng.",
    ),
    Demand(
        id="dm-004",
        author_name="Ngọc Phương",
        author_initials="NP",
        posted_label="hôm qua",
        summary="Suất nội bộ căn hộ 2PN, sổ hồng cầm tay, khu vực trung tâm.",
    ),
]

_MARKET_BARS: list[MarketBar] = [
    MarketBar(kind=PropertyKind.HOUSE, label="Nhà riêng", value=3635, color="#e88a1e"),
    MarketBar(kind=PropertyKind.APARTMENT, label="Căn hộ chung cư", value=1871, color="#2f7bef"),
    MarketBar(kind=PropertyKind.LAND, label="Đất", value=1189, color="#e2536f"),
    MarketBar(kind=PropertyKind.VILLA, label="Biệt thự liền kề", value=436, color="#28a684"),
    MarketBar(kind=PropertyKind.SHOPHOUSE, label="Shophouse", value=188, color="#e5b93b"),
]


class InMemoryPortalRepository:
    """Dữ liệu mẫu trong bộ nhớ — thay bằng SQL khi có DB thật."""

    async def list_listings(self, *, listing_type: ListingType | None = None, limit: int = 20) -> list[Listing]:
        items = _LISTINGS
        if listing_type is not None:
            items = [item for item in items if item.listing_type == listing_type]
        return items[:limit]

    async def list_projects(self, *, limit: int = 20) -> list[Project]:
        return _PROJECTS[:limit]

    async def list_demands(self, *, limit: int = 20) -> list[Demand]:
        return _DEMANDS[:limit]

    async def market_stats(self) -> MarketStats:
        return MarketStats(
            as_of=date.today(),
            active_listings=153_838,
            listings_today=sum(bar.value for bar in _MARKET_BARS),
            bars=_MARKET_BARS,
        )
