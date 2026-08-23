"""SalesMate backend — FastAPI.

Chạy:  cd interface/backend && uvicorn app.main:app --reload
Docs:  http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import close_pool, open_pool
from app.routers import apartments, auth, chat, dat_coc, documents, images, news, sales, tai_lieu, users, zones

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    problems = settings.config_problems()
    if problems:
        raise RuntimeError(
            "Cấu hình chưa hợp lệ:\n- "
            + "\n- ".join(problems)
            + "\nCopy .env.example ở gốc repo thành .env rồi điền giá trị."
        )

    open_pool()
    if not settings.storage_enabled:
        logger.warning("Chưa cấu hình Supabase Storage — chức năng upload file sẽ báo lỗi.")
    if not settings.chat_enabled:
        logger.warning("Chưa có AI_CORE_URL — /api/chat sẽ báo lỗi.")
    else:
        logger.info("Chat sẽ đi qua lõi AI tại %s", settings.ai_core_url)

    # KHÔNG đánh thức lõi AI từ đây. Đo được trên Render: request đi từ trong
    # nền tảng sang URL công khai của một service free đang ngủ trả 502/429
    # trong dưới 5 giây và KHÔNG kích hoạt spin-up, trong khi cùng URL đó gọi
    # từ máy ngoài trả 200 sau ~42 giây. Việc đánh thức phải đến từ bên ngoài:
    # job cron (DEPLOY.md) và trình duyệt của khách khi mở widget.
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="SalesMate API",
    description="Backend cho web hỗ trợ sale bán căn hộ. Auth bằng JWT, phân quyền admin/sale.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(apartments.router)
app.include_router(zones.router)
app.include_router(sales.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(images.router)
app.include_router(dat_coc.router)
app.include_router(tai_lieu.router)
app.include_router(news.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log đầy đủ ở server, ra ngoài chỉ một câu — không lộ stack trace."""
    logger.exception("Lỗi chưa xử lý tại %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Hệ thống gặp sự cố. Thử lại sau, nếu vẫn lỗi báo quản trị viên."},
    )


@app.get("/api/health", tags=["health"])
def health() -> dict[str, object]:
    """Kiểm tra backend sống và cấu hình đã đủ chưa.

    Đây cũng là đích của job cron giữ service khỏi ngủ trên gói free Render —
    xem DEPLOY.md. Endpoint phải nhẹ và KHÔNG chạm database: nó bị gọi mỗi 5
    phút suốt ngày đêm.

    `ai_core_url` trả ra để widget tự đánh thức lõi AI từ TRÌNH DUYỆT. Đó là
    URL công khai, không phải bí mật. Không hardcode ở frontend vì nó khác nhau
    giữa máy mình và Render, và đổi URL mà quên sửa hai chỗ là lỗi câm.
    """
    return {
        "status": "ok",
        "storage_enabled": settings.storage_enabled,
        "chat_enabled": settings.chat_enabled,
        "ai_core_url": settings.ai_core_url.rstrip("/"),
    }
