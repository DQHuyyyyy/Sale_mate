"""Tool thống kê tồn kho — trả lời câu hỏi về SỐ LƯỢNG, không phải từng căn.

Vì sao cần tool riêng: `inventory_lookup` tra một hoặc vài căn cụ thể, còn "còn
bao nhiêu căn chưa bán" là câu hỏi tổng hợp. Nhét cả trăm dòng vào prompt rồi
bắt model tự đếm là vừa tốn token vừa dễ đếm sai — model đếm kém, SQL thì không.

Đếm trong Python thay vì thêm hàm vào `InventoryDB`: `query_units()` sẵn có đã
trả đủ dòng, tồn kho chỉ khoảng trăm căn nên gom lại không đáng kể, và làm vậy
thì không phải đụng vào module của Data.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.tools.registry import register_tool
from src.data.stores.inventory_db import get_inventory_db

_CON_HANG = "available"

# Câu hỏi tổng hợp: hỏi số lượng, hỏi "còn bao nhiêu", hỏi tổng quan tồn kho.
_DAU_HIEU = (
    "bao nhiêu căn",
    "còn bao nhiêu",
    "số lượng căn",
    "mấy căn",
    "tổng số căn",
    "còn mấy",
    "chưa bán",
    "chưa được bán",
    "đã bán",
    "tồn kho",
    "thống kê",
)

_MA_CAN = re.compile(r"\b[A-Za-z]{2,4}\d{2,5}\b")


def _extract_args(query: str) -> dict[str, Any] | None:
    """Chỉ chạy với câu hỏi tổng hợp, và không có mã căn cụ thể.

    Có mã căn nghĩa là người dùng hỏi về đúng căn đó — việc của
    `inventory_lookup`, không phải đếm cả kho.
    """
    thap = query.lower()
    if _MA_CAN.search(query):
        return None
    if not any(dau in thap for dau in _DAU_HIEU):
        return None
    return {}


class SummaryArgs(BaseModel):
    building: str | None = Field(default=None, description="Chỉ đếm trong một toà, ví dụ 'S210'")
    unit_type: str | None = Field(default=None, description="Chỉ đếm một loại căn, ví dụ '2PN'")


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_extract_args)
class InventorySummaryTool(AgentTool):
    """Thống kê tồn kho theo số lượng."""

    name = "inventory_summary"
    description = (
        "Đếm số căn còn trống / đã bán trong tồn kho, tổng hợp theo toà và loại căn. "
        "Dùng khi người dùng hỏi SỐ LƯỢNG — 'còn bao nhiêu căn chưa bán', "
        "'toà S210 còn mấy căn' — chứ không hỏi về một căn cụ thể."
    )
    args_schema = SummaryArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args = SummaryArgs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        try:
            records = await asyncio.to_thread(
                get_inventory_db().query_units,
                building=args.building,
                unit_type=args.unit_type,
            )
        except Exception as exc:  # noqa: BLE001 - lỗi kết nối DB, không làm đứt luồng
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        if not records:
            return ToolResult(
                ok=True,
                data={},
                source="inventory:postgres",
                error="Không có căn nào khớp điều kiện.",
            )

        return ToolResult(ok=True, data=self._thong_ke(records), source="inventory:postgres")

    @staticmethod
    def _thong_ke(records: list[dict[str, Any]]) -> dict[str, Any]:
        con = [r for r in records if r.get("status") == _CON_HANG]
        return {
            "tong_so_can": len(records),
            "con_trong": len(con),
            "da_ban": len(records) - len(con),
            # Chỉ thống kê phần CÒN TRỐNG theo toà/loại: sale cần biết còn gì để
            # chào khách, không cần phân bố của những căn đã bán.
            "con_trong_theo_toa": dict(sorted(Counter(r.get("building") for r in con).items())),
            "con_trong_theo_loai": dict(sorted(Counter(r.get("unit_type") for r in con).items())),
        }
