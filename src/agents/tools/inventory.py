"""Tool tra tồn kho căn hộ — query bảng `inventory_units` trong Postgres thật.

Tồn kho là dữ liệu CÓ CẤU TRÚC (giá, diện tích, tình trạng...) nên đi qua
Postgres + SQL, KHÁC văn bản dài (chính sách, tiện ích, pháp lý...) đi qua
Qdrant + vector search — xem src/data/stores/inventory_db.py để biết vì sao
tách hai đường đi này. Không nhét giá/tình trạng vào RAG — hai trường đó chỉ
có ở đây, tránh hai nguồn số liệu lệch nhau theo thời gian.

Trước đây tool này đọc thẳng CSV mỗi lần gọi (không có DB); giờ query SQL
thật. Nạp/cập nhật dữ liệu vào bảng qua scripts/migrate_inventory_to_postgres.py
— gần nhất với "thời gian thực" khi hệ thống chưa có ERP ghi trực tiếp vào
bảng này.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.tools.registry import register_tool
from src.data.stores.inventory_db import get_inventory_db

_STATUS_LABEL = {
    "available": "Còn trống",
    "reserved": "Giữ chỗ",
    "sold": "Đã bán",
}

# Mã căn: 2-4 chữ cái rồi 2-5 chữ số, ví dụ VOP345. Bao bằng \b để "VOP345"
# trong câu dài vẫn bắt được, còn "abcVOP345" thì không.
_UNIT_CODE = re.compile(r"\b([A-Za-z]{2,4}\d{2,5})\b")


def _extract_args(query: str) -> dict[str, Any] | None:
    """Rút mã căn từ câu hỏi. Không có mã thì trả None — tool không chạy.

    Cố ý CHỈ nhận mã căn, không đoán toà hay loại căn từ ngôn ngữ tự nhiên.
    Tra sai một căn rồi báo giá cho khách còn tệ hơn là không tra. Khi nào cần
    lọc theo toà/loại, thêm một tool riêng với schema rõ ràng.
    """
    match = _UNIT_CODE.search(query)
    if match is None:
        return None
    return {"unit_code": match.group(1).upper()}


class InventoryArgs(BaseModel):
    unit_code: str | None = Field(default=None, description="Mã căn cụ thể, ví dụ 'VOP398'")
    building: str | None = Field(default=None, description="Toà nhà, ví dụ 'R103'")
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN' (khớp gần đúng)")


def _to_row(record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "status_label": _STATUS_LABEL.get(record["status"], record["status"])}


# LISTING và PRICE là hai nhãn mà câu hỏi về một căn cụ thể hay rơi vào. Khai
# rộng không sao: _extract_args mới là cửa quyết định, không có mã căn thì
# tool không chạy.
@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_extract_args)
class InventoryLookupTool(AgentTool):
    """Tra tình trạng căn hộ tồn kho thật theo mã căn / toà / loại căn."""

    name = "inventory_lookup"
    description = (
        "Tra tình trạng căn hộ THẬT theo thời gian thực (Còn trống / Giữ chỗ / Đã bán), "
        "kèm giá — từ tồn kho nội bộ. Dùng khi người dùng hỏi còn căn nào trống, "
        "giá/tình trạng một căn cụ thể theo mã căn hoặc toà nhà."
    )
    args_schema = InventoryArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args = InventoryArgs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        try:
            records = await asyncio.to_thread(
                get_inventory_db().query_units,
                unit_code=args.unit_code,
                building=args.building,
                unit_type=args.unit_type,
            )
        except Exception as exc:  # noqa: BLE001 - lỗi kết nối DB, không làm đứt luồng agent
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        if not records:
            return ToolResult(
                ok=True,
                data=[],
                source="inventory:postgres",
                error="Không tìm thấy căn nào khớp điều kiện.",
            )

        return ToolResult(ok=True, data=[_to_row(r) for r in records], source="inventory:postgres")
