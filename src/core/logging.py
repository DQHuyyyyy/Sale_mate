"""Structured logging dạng JSON.

Log JSON để sau này đẩy thẳng vào công cụ giám sát mà không phải parse text.
Không bao giờ log giá trị nhạy cảm (API key, mật khẩu, token).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_NOISY_LIBRARIES = ("httpx", "httpcore", "urllib3", "openai", "qdrant_client")

# Context của lượt hỏi hiện tại, tự động gắn vào mọi dòng log trong lượt đó.
# Dùng ContextVar chứ không dùng biến toàn cục: mỗi request async có bản riêng,
# hai người hỏi cùng lúc không trộn log của nhau.
trace_context: ContextVar[dict[str, Any]] = ContextVar("trace_context", default={})


@contextmanager
def trace(**fields: Any) -> Iterator[None]:
    """Gắn các trường này vào mọi log phát ra bên trong khối.

    Dùng:
        with trace(session_id=sid):
            ...   # mọi log ở đây đều có session_id
    """
    token = trace_context.set({**trace_context.get(), **fields})
    try:
        yield
    finally:
        trace_context.reset(token)


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

        # Gộp context của lượt hỏi (session_id) với context riêng của dòng log.
        # Nhờ vậy lọc log theo một session là thấy đủ đường đi của câu hỏi đó:
        # router → tools → retrieve → generate, kèm thời gian từng chặng.
        context = {**trace_context.get(), **(getattr(record, "context", None) or {})}
        if context:
            entry["context"] = context

        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, ensure_ascii=False)


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler không bao giờ làm sập app vì lỗi mã hoá.

    Vì sao cần: log của hệ thống này toàn tiếng Việt. Nếu stdout không phải UTF-8
    (console Windows cp1252, hoặc stream đã bị wrap trong Docker/CI), việc ghi
    log sẽ ném UnicodeEncodeError — tức là chính công cụ chẩn đoán lại trở thành
    nguồn lỗi. Ở đây ta lùi về dạng ASCII-escaped (\\uXXXX): xấu mắt hơn nhưng
    vẫn là JSON hợp lệ và không mất thông tin.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                message = self.format(record)
                escaped = message.encode("unicode_escape").decode("ascii")
                self.stream.write(escaped + self.terminator)
                self.flush()
            except Exception:  # noqa: BLE001 - log hỏng thì thôi, đừng làm sập app
                self.handleError(record)


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

    handler = SafeStreamHandler(stream)
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
