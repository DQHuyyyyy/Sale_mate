"""Structured logging dạng JSON.

Log JSON để sau này đẩy thẳng vào công cụ giám sát mà không phải parse text.
Không bao giờ log giá trị nhạy cảm (API key, mật khẩu, token).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_NOISY_LIBRARIES = ("httpx", "httpcore", "urllib3", "openai", "qdrant_client")


class JSONFormatter(logging.Formatter):
    """Đưa mỗi bản ghi log thành một dòng JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        context = getattr(record, "context", None)
        if context:
            entry["context"] = context

        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Cấu hình root logger. Gọi một lần lúc app khởi động."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for existing in list(root.handlers):
        root.removeHandler(existing)

    # Console Windows mặc định là cp1252, không mã hoá được tiếng Việt và làm
    # chính hệ thống log đổ lỗi UnicodeEncodeError. Ép UTF-8 cho chắc.
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # stream đã bị thay bằng thứ không đổi được
            pass

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    for name in _NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger cho một module. Dùng: logger = get_logger(__name__)."""
    return logging.getLogger(name)


def log_context(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Ghi log kèm dữ liệu có cấu trúc.

    Ví dụ:
        log_context(logger, logging.INFO, "Chat bắt đầu", session_id=sid, chars=len(msg))
    """
    logger.log(level, message, extra={"context": fields})
