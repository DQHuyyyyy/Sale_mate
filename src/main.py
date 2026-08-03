"""Điểm vào ứng dụng FastAPI.

Chạy dev:  uvicorn src.main:app --reload
Tài liệu:  http://localhost:8000/docs
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import register_error_handlers
from src.api.v1 import router as v1_router
from src.bootstrap import configure
from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo tài nguyên một lần lúc app start, dọn dẹp lúc stop."""
    settings = get_settings()
    setup_logging(settings.log_level)
    configure()
    logger.info(
        "Khởi động %s",
        settings.app_name,
        extra={"context": {"env": settings.app_env}},
    )
    yield
    logger.info("Tắt ứng dụng")


settings = get_settings()

app = FastAPI(
    title="SalesMate API",
    description="Nền tảng bất động sản xác thực kèm trợ lý AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(v1_router, prefix="/api/v1")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Ghi log mọi request kèm thời gian xử lý."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "context": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round(elapsed_ms, 1),
            }
        },
    )
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.0f}"
    return response


@app.get("/health", tags=["health"], summary="Health check ở gốc")
async def root_health() -> dict[str, str]:
    """Giữ ở gốc để Docker HEALTHCHECK và uptime monitor gọi đơn giản."""
    return {"status": "ok", "environment": settings.app_env}
