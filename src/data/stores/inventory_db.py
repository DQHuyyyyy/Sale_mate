"""Lưu tồn kho căn hộ (dữ liệu CÓ CẤU TRÚC) trong Postgres — khác văn bản dài
(chính sách, tiện ích...) đi qua Qdrant/vector search. Hai loại dữ liệu, hai
đường đi khác nhau: có cấu trúc → Postgres + SQL, văn bản dài → Qdrant + RAG.

Trước đây `InventoryLookupTool` đọc thẳng CSV mỗi lần gọi; giờ CSV chỉ còn là
nguồn dữ liệu là VIEW `inventory_units` trên `salemate_v1` (migration 005), còn tool tra
cứu thật sự query bảng `inventory_units` trong Postgres (Supabase).

Dùng SQLAlchemy Core (không ORM) — bảng định nghĩa portable giữa SQLite (test,
không gọi DB thật đúng quy ước dự án) và Postgres (thật). Upsert viết bằng
DELETE+INSERT thay vì cú pháp `ON CONFLICT` riêng của Postgres, để logic giống
hệt nhau trên cả hai backend.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import JSON, Column, MetaData, Numeric, String, Table, create_engine, or_, select
from sqlalchemy.engine import Engine

from src.core.config import get_settings
from src.data.sources.inventory import InventoryUnit

metadata = MetaData()

inventory_units_table = Table(
    "inventory_units",
    metadata,
    Column("unit_code", String, primary_key=True),
    Column("building", String),
    Column("floor", String),
    Column("room_no", String),
    Column("unit_type", String),
    Column("area_m2", String),
    Column("direction", String),
    Column("view", String),
    Column("legal_status", String),
    Column("price_label", String),
    Column("furniture", String),
    Column("status", String),
    Column("photos", JSON),
    # Hai cột SỐ, do view sinh từ salemate_v1 (migration 007). Có chúng thì lọc
    # theo khoảng giá / diện tích dùng số thật, không phải parse "2,120 tỷ".
    # Nullable: SQLite trong test không có view nên để trống, và tool coi
    # None là "không rõ" chứ không phải 0.
    Column("price_value", Numeric),  # đơn vị: tỷ đồng
    Column("area_value", Numeric),  # đơn vị: m2
    # Phân khu: Ocean Park 1 / 2 / 3 (migration 008). Gán theo TOÀ nên mọi căn
    # cùng toà luôn cùng phân khu. Hiện là dữ liệu DEMO, chưa phải số liệu thật.
    Column("subdivision", String),
)


class InventoryDB:
    """Truy cập bảng `inventory_units`. Mọi thao tác đồng bộ (SQLAlchemy Core
    chưa cần async driver) — bên gọi async (tool) tự bọc `asyncio.to_thread`.
    """

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(database_url)

    def ensure_table(self) -> None:
        metadata.create_all(self._engine, tables=[inventory_units_table])

    def upsert_units(self, units: list[InventoryUnit]) -> int:
        """Nạp/cập nhật toàn bộ căn — idempotent, chạy lại bao nhiêu lần cũng an toàn."""
        if not units:
            return 0
        self.ensure_table()
        rows = [
            {
                "unit_code": u.unit_code,
                "building": u.building,
                "floor": u.floor,
                "room_no": u.room_no,
                "unit_type": u.unit_type,
                "area_m2": u.area_m2,
                "direction": u.direction,
                "view": u.view,
                "legal_status": u.legal_status,
                "price_label": u.price_label,
                "furniture": u.furniture,
                "status": u.status,
                "photos": u.photos,
            }
            for u in units
        ]
        codes = [row["unit_code"] for row in rows]
        with self._engine.begin() as conn:
            conn.execute(inventory_units_table.delete().where(inventory_units_table.c.unit_code.in_(codes)))
            conn.execute(inventory_units_table.insert(), rows)
        return len(rows)

    def query_units(
        self,
        *,
        unit_code: str | None = None,
        unit_codes: list[str] | None = None,
        building: str | None = None,
        unit_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Tra căn theo mã, danh sách mã, toà hoặc loại căn.

        `unit_codes` cho tool so sánh lấy nhiều căn trong MỘT truy vấn. Dùng
        `ilike` từng mã thay vì `in_` để giữ đúng ngữ nghĩa không phân biệt hoa
        thường của nhánh một mã — dữ liệu ghi mã căn không thống nhất.
        """
        self.ensure_table()
        stmt = select(inventory_units_table)
        if unit_code is not None:
            stmt = stmt.where(inventory_units_table.c.unit_code.ilike(unit_code))
        if unit_codes:
            stmt = stmt.where(or_(*[inventory_units_table.c.unit_code.ilike(m) for m in unit_codes]))
        if building is not None:
            stmt = stmt.where(inventory_units_table.c.building.ilike(building))
        if unit_type is not None:
            stmt = stmt.where(inventory_units_table.c.unit_type.ilike(f"%{unit_type}%"))

        with self._engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt)]


@lru_cache
def get_inventory_db() -> InventoryDB:
    """Singleton theo tiến trình — tránh tạo engine/connection pool mới mỗi lần tool được gọi."""
    return InventoryDB(get_settings().database_url)
