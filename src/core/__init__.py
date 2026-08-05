"""Cross-cutting concerns: cấu hình, logging, lỗi, dependency container.

Tầng này KHÔNG được import từ src.data / src.agents / src.api để tránh vòng lặp.
Việc gắn interface với implementation nằm ở src/bootstrap.py.
"""

from src.core.config import Settings, get_settings
from src.core.container import Container, container
from src.core.exceptions import (
    AgentTimeoutError,
    ConfigurationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    SalesMateError,
    UnauthorizedError,
    UpstreamError,
    ValidationFailedError,
)
from src.core.logging import get_logger, setup_logging

__all__ = [
    "AgentTimeoutError",
    "ConfigurationError",
    "Container",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "SalesMateError",
    "Settings",
    "UnauthorizedError",
    "UpstreamError",
    "ValidationFailedError",
    "container",
    "get_logger",
    "get_settings",
    "setup_logging",
]
