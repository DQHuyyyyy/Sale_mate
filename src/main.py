"""Điểm vào ứng dụng FastAPI.

Chạy dev:  uvicorn src.main:app --reload
Tài liệu:  http://localhost:8000/docs
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.agents.prompts import SYSTEM_PROMPT_VERSION
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
    setup_logging(settings.log_level, thu_muc_nhat_ky=settings.log_dir or None)
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


@app.get("/health/config", tags=["health"], summary="Cấu hình đang chạy thật")
async def config_dang_chay() -> dict[str, object]:
    """Cấu hình mà tiến trình NÀY đang chạy — để so local với production.

    Vì sao cần: biến môi trường của Render nằm trong dashboard, không ai đọc
    được từ repo, và biến nào không khai thì code lặng lẽ lấy giá trị mặc định.
    Hệ quả đã xảy ra thật: local bật `ENABLE_AGENT_LOOP` và chạy model trả lời
    đắt, prod không khai biến nào trong hai cái đó nên rơi về `False` và một
    model rẻ hơn — cùng một câu hỏi cho ra hai chất lượng khác hẳn, không dấu hiệu.
    Đoán mò hai bên lệch chỗ nào tốn nhiều thời gian hơn hẳn một endpoint.

    CHỈ trả tên cấu hình và cờ có/không, KHÔNG trả giá trị bí mật: khoá API và
    chuỗi kết nối chỉ hiện dưới dạng boolean. Endpoint này công khai như
    `/health`, nên bất kỳ thứ gì trả về ở đây là công khai.
    """
    return {
        "environment": settings.app_env,
        "model": {
            "tra_loi": settings.llm_model_answer,
            "nhanh": settings.llm_model_fast,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "co_openai_key": bool(settings.openai_api_key),
        },
        "agent": {
            "vong_lap": settings.enable_agent_loop,
            "so_lan_lap_toi_da": settings.agent_max_iterations,
            "prompt": SYSTEM_PROMPT_VERSION,
        },
        "leo_thang": {
            # Cổng leo thang chạy hay không phụ thuộc BA thứ, thiếu một là nó
            # im lặng không chạy và dấu hiệu duy nhất là hoá đơn Anthropic bằng
            # 0. Trả cả ba ra đây để không phải đoán.
            "bat": settings.enable_orchestrator,
            "che_do": settings.che_do_leo_thang,
            "model": settings.orchestrator_model,
            "co_anthropic_key": settings.has_anthropic_key,
            "ngan_sach_ngay_usd": settings.orchestrator_daily_budget_usd,
            # `build_graph` ưu tiên vòng lặp cũ, nên bật cả hai cờ thì node
            # orchestrate dựng ra mà không có cạnh nào dẫn tới. True ở đây =
            # đang trả tiền cho một tính năng không lượt nào chạy qua.
            "bi_vong_lap_che": settings.enable_orchestrator and settings.enable_agent_loop,
        },
        "rag": {
            "bat": settings.enable_rag,
            "reranker": settings.reranker,
            "top_k": settings.retrieval_top_k,
            "nguong_do_phu": settings.coverage_threshold,
            "collection": settings.qdrant_collection,
            "co_qdrant": bool(settings.qdrant_url) and "localhost" not in settings.qdrant_url,
        },
        "ton_kho": {
            # Rơi về SQLite nghĩa là tool tồn kho tra một file rỗng trong
            # container và trợ lý trả lời "chưa đủ dữ liệu" cho mọi câu hỏi căn.
            "dung_postgres": settings.database_url.startswith("postgres"),
        },
    }
