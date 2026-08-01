"""Lớp cơ sở cho node — Template Method pattern.

BaseNode lo phần lặp lại: bắt lỗi, ghi log, đo thời gian. Node con chỉ viết
đúng phần logic của mình trong execute(). Nhờ vậy không node nào quên
try/except và không ai copy-paste boilerplate.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from src.agents.state import AgentState
from src.core.exceptions import SalesMateError
from src.core.logging import get_logger

logger = get_logger(__name__)


class BaseNode(ABC):
    """Node của LangGraph, gọi được như một hàm async."""

    name: str = "node"

    @abstractmethod
    async def execute(self, state: AgentState) -> dict[str, Any]:
        """Logic thật của node. Chỉ trả về những trường cần cập nhật."""

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = await self.execute(state)
        except SalesMateError:
            # Lỗi nghiệp vụ đã có thông điệp tiếng Việt và HTTP status đúng —
            # để nó đi tiếp lên tầng API thay vì nuốt thành "lỗi chung chung".
            raise
        except Exception as exc:  # noqa: BLE001 - biên node: không để rơi ra ngoài graph
            logger.exception("Node %s lỗi", self.name, extra={"context": {"node": self.name}})
            return {"error": f"{self.name}: {exc}"}

        elapsed_ms = (time.perf_counter() - started) * 1000
        metadata = dict(state.get("metadata", {}))
        metadata[f"{self.name}_ms"] = round(elapsed_ms, 1)
        result.setdefault("metadata", metadata)
        logger.debug("Node %s xong", self.name, extra={"context": {"node": self.name, "ms": elapsed_ms}})
        return result
