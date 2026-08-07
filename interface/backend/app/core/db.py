"""Kết nối Supabase PostgreSQL bằng psycopg 3 + connection pool."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# prepare_threshold=None: Supabase pooler ở chế độ transaction không giữ được
# prepared statement giữa các lượt, tắt đi cho chắc.
pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=10,
    max_idle=300,
    open=False,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
)


def open_pool() -> None:
    pool.open()
    logger.info("Đã mở connection pool tới database")


def close_pool() -> None:
    pool.close()
    logger.info("Đã đóng connection pool")


@contextmanager
def get_conn() -> Iterator:
    """Mượn một connection từ pool. Commit khi thoát bình thường, rollback khi lỗi."""
    with pool.connection() as conn:
        yield conn


def fetch_all(sql: str, params: tuple | dict | None = None) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch_one(sql: str, params: tuple | dict | None = None) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql: str, params: tuple | dict | None = None) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount
