"""Tool tra tồn kho căn hộ — đọc dữ liệu tồn kho THẬT từ data/raw/inventory.csv.

Tồn kho là dữ liệu ĐỘNG (giá/tình trạng đổi theo phút), nên đi qua tool chứ
không nhét vào vector store (RAG luôn là bản chụp cũ — xem
src/data/sources/inventory.py, phần view/nội thất/pháp lý mới vào RAG, giá và
tình trạng cố tình KHÔNG vào RAG để tránh hai nguồn số liệu lệch nhau).

Đọc lại CSV ở MỖI lần gọi (không cache trong tiến trình) — gần nhất với "thời
gian thực" khi hệ thống chưa có DB/ERP thật kết nối trực tiếp (mục 9 Data
Handling — phần nối API doanh nghiệp thật vẫn cần team quyết định, ngoài khả
năng solo vì chưa có ERP để nối).

Trước đây tool này trả dữ liệu mock hoàn toàn hư cấu ("Lakeside Metropole",
"The Origin Riverside") không liên quan gì tới tồn kho Vinhomes Ocean Park
thật — đã phát hiện và sửa.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.tools.registry import register_tool
from src.data.sources.inventory import InventoryUnit, load_inventory_csv

_STATUS_LABEL = {
    "available": "Còn trống",
    "reserved": "Giữ chỗ",
    "sold": "Đã bán",
}


class InventoryArgs(BaseModel):
    unit_code: str | None = Field(default=None, description="Mã căn cụ thể, ví dụ 'VOP398'")
    building: str | None = Field(default=None, description="Toà nhà, ví dụ 'R103'")
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN' (khớp gần đúng)")


def _to_row(unit: InventoryUnit) -> dict[str, Any]:
    return {
        "unit_code": unit.unit_code,
        "building": unit.building,
        "floor": unit.floor,
        "unit_type": unit.unit_type,
        "area_m2": unit.area_m2,
        "direction": unit.direction,
        "status": unit.status,
        "status_label": _STATUS_LABEL.get(unit.status, unit.status),
        "price_label": unit.price_label,
    }


@register_tool
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
            units = load_inventory_csv()
        except FileNotFoundError:
            return ToolResult.failure(
                "Chưa có dữ liệu tồn kho (data/raw/inventory.csv) trên máy này — "
                "cần tải file từ Drive về trước khi tra cứu."
            )

        matches = [
            unit
            for unit in units
            if (args.unit_code is None or unit.unit_code.lower() == args.unit_code.lower())
            and (args.building is None or unit.building.lower() == args.building.lower())
            and (args.unit_type is None or args.unit_type.lower() in unit.unit_type.lower())
        ]

        if not matches:
            return ToolResult(
                ok=True,
                data=[],
                source="inventory:csv",
                error="Không tìm thấy căn nào khớp điều kiện.",
            )

        return ToolResult(ok=True, data=[_to_row(unit) for unit in matches], source="inventory:csv")
