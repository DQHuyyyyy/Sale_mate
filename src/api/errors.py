"""Đổi lỗi nghiệp vụ thành HTTP response.

Nguyên tắc: KHÔNG BAO GIỜ lộ stack trace hay thông báo lỗi nội bộ ra ngoài.
Người dùng nhận thông điệp tiếng Việt nói rõ chuyện gì và làm gì tiếp.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.exceptions import SalesMateError
from src.core.logging import get_logger

logger = get_logger(__name__)


async def salesmate_error_handler(request: Request, exc: SalesMateError) -> JSONResponse:
    logger.warning(
        "Lỗi nghiệp vụ",
        extra={"context": {"code": exc.code, "path": request.url.path}},
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 của Pydantic — nói rõ trường nào sai, bằng tiếng Việt."""
    fields = [".".join(str(part) for part in err["loc"][1:]) for err in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_failed",
                "message": "Dữ liệu gửi lên chưa hợp lệ. Vui lòng kiểm tra lại.",
                "detail": {"fields": fields},
            }
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lưới cuối. Log đầy đủ ở server, trả về thông điệp chung cho client."""
    logger.exception("Lỗi không lường trước", extra={"context": {"path": request.url.path}})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Hệ thống đang gặp sự cố. Vui lòng thử lại sau ít phút.",
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SalesMateError, salesmate_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
