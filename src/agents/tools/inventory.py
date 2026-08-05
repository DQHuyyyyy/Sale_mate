"""Tool tra tồn kho căn hộ — hiện dùng dữ liệu mock.

Tồn kho là dữ liệu ĐỘNG, thay đổi theo phút, nên đi qua tool chứ không nhét vào
vector store (RAG luôn là bản chụp cũ). Khi có DB thật, chỉ đổi phần thân
InventoryLookupTool.run() — chữ ký và ToolResult giữ nguyên.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.tools.registry import register_tool

# Dữ liệu mock — thay bằng truy vấn DB khi có.
_MOCK_INVENTORY: list[dict[str, Any]] = [
    {
        "project": "Lakeside Metropole",
        "building": "A",
        "unit_code": "A-12-05",
        "unit_type": "2PN",
        "area_m2": 68,
        "status": "available",
        "price_label": "3,85 tỷ",
    },
    {
        "project": "Lakeside Metropole",
        "building": "A",
        "unit_code": "A-15-02",
        "unit_type": "3PN",
        "area_m2": 95,
        "status": "reserved",
        "price_label": "5,40 tỷ",
    },
    {
        "project": "The Origin Riverside",
        "building": "B",
        "unit_code": "B-08-11",
        "unit_type": "3PN",
        "area_m2": 88,
        "status": "sold",
        "price_label": "4,20 tỷ",
    },
]

_STATUS_LABEL = {
    "available": "Còn trống",
    "reserved": "Giữ chỗ",
    "sold": "Đã bán",
}


class InventoryArgs(BaseModel):
    project: str = Field(description="Tên dự án")
    building: str | None = Field(default=None, description="Toà nhà")
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN'")


@register_tool
class InventoryLookupTool(AgentTool):
    """Tra trạng thái căn theo dự án / toà / loại căn."""

    name = "inventory_lookup"
    description = (
        "Tra tình trạng căn hộ theo thời gian thực (Còn trống / Giữ chỗ / Đã bán). "
        "Dùng khi người dùng hỏi còn căn nào, căn nào trống, tình trạng căn cụ thể."
    )
    args_schema = InventoryArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args = InventoryArgs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        matches = [
            {**row, "status_label": _STATUS_LABEL[row["status"]]}
            for row in _MOCK_INVENTORY
            if row["project"].lower() == args.project.lower()
            and (args.building is None or row["building"] == args.building)
            and (args.unit_type is None or row["unit_type"] == args.unit_type)
        ]

        if not matches:
            return ToolResult(
                ok=True,
                data=[],
                source="inventory:mock",
                error="Không tìm thấy căn nào khớp điều kiện.",
            )

        return ToolResult(ok=True, data=matches, source="inventory:mock")
