"""Di chuyển tồn kho từ CSV sang bảng `inventory_units` trong Postgres (Supabase).

Đúng kiến trúc "hai loại dữ liệu, hai đường đi": dữ liệu CÓ CẤU TRÚC (mã, giá,
diện tích...) đi qua Postgres + SQL — khác văn bản dài (chính sách, tiện ích)
đi qua Qdrant + vector search (xem scripts/ingest_knowledge_docs.py).

Idempotent — chạy lại bao nhiêu lần cũng an toàn (upsert theo unit_code).

Chạy (cần DATABASE_URL trong .env trỏ đúng Supabase Postgres):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/migrate_inventory_to_postgres.py
"""

from __future__ import annotations

import asyncio

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.sources.inventory import load_inventory_csv
from src.data.stores.inventory_db import InventoryDB


async def main() -> None:
    setup_logging("INFO")
    logger = get_logger(__name__)
    settings = get_settings()

    units = load_inventory_csv()
    logger.info("Đọc được %d căn từ CSV", len(units))

    db = InventoryDB(settings.database_url)
    count = await asyncio.to_thread(db.upsert_units, units)
    logger.info("Đã nạp %d căn vào Postgres (bảng inventory_units)", count)

    sample = await asyncio.to_thread(db.query_units)
    logger.info("Kiểm tra lại: query trả về %d dòng từ Postgres", len(sample))


if __name__ == "__main__":
    asyncio.run(main())
