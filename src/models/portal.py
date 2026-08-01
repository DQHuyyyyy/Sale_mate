"""DTO cho dữ liệu portal bất động sản (trang chủ).

Khớp 1-1 với các component trong Giaodien.md mục 4:
ListingCard · ProjectCard · DemandCard · MarketPanel.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ListingType(StrEnum):
    """Tab trong khối 'Bất động sản nổi bật'."""

    SALE = "sale"  # Mua bán
    RENT = "rent"  # Cho thuê
    TRANSFER = "transfer"  # Sang nhượng


class PropertyKind(StrEnum):
    """Loại hình — dùng cho biểu đồ cột ở MarketPanel."""

    HOUSE = "house"  # Nhà riêng
    APARTMENT = "apartment"  # Căn hộ chung cư
    LAND = "land"  # Đất
    VILLA = "villa"  # Biệt thự liền kề
    SHOPHOUSE = "shophouse"  # Shophouse


class Listing(BaseModel):
    """Một tin đăng — render bằng ListingCard."""

    id: str
    title: str
    listing_type: ListingType = ListingType.SALE
    kind: PropertyKind = PropertyKind.APARTMENT
    price_label: str = Field(description="Giá đã format kiểu VN, ví dụ '3,85 tỷ'")
    unit_price_label: str = Field(default="", description="Đơn giá, ví dụ '56 tr/m²'")
    area_label: str = Field(default="", description="Ví dụ '68 m²'")
    bedrooms_label: str = Field(default="", description="Ví dụ '2 PN'")
    location: str = ""
    is_verified: bool = Field(default=False, description="Hiện badge 'Xác thực' xanh lá")
    photo_count: int = 0
    image_url: str | None = None


class Project(BaseModel):
    """Một dự án — render bằng ProjectCard."""

    id: str
    name: str
    developer: str = Field(default="", description="Chủ đầu tư")
    location: str = ""
    price_from_label: str = Field(default="", description="Ví dụ '3,2 tỷ'")
    image_url: str | None = None


class Demand(BaseModel):
    """Nhu cầu người dùng đăng — render bằng DemandCard."""

    id: str
    author_name: str
    author_initials: str = Field(description="2 chữ cái hiện trong avatar tròn")
    posted_label: str = Field(description="Ví dụ '2 giờ trước'")
    summary: str


class MarketBar(BaseModel):
    """Một cột trong biểu đồ 'Thống kê tin đăng trong ngày'."""

    kind: PropertyKind
    label: str
    value: int
    color: str = Field(description="Mã màu hex cho cột và chú giải")


class MarketStats(BaseModel):
    """Panel 'Thị trường hôm nay' ở hero."""

    as_of: date
    active_listings: int = Field(description="Tin đang hiệu lực")
    listings_today: int = Field(description="Tin đăng hôm nay")
    bars: list[MarketBar] = Field(default_factory=list)


class Page(BaseModel, Generic[T]):
    """Bọc kết quả có phân trang."""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total
