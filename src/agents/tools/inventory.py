"""Tool tra tồn kho căn hộ — query bảng `inventory_units` trong Postgres thật.

Tồn kho là dữ liệu CÓ CẤU TRÚC (giá, diện tích, tình trạng...) nên đi qua
Postgres + SQL, KHÁC văn bản dài (chính sách, tiện ích, pháp lý...) đi qua
Qdrant + vector search — xem src/data/stores/inventory_db.py để biết vì sao
tách hai đường đi này. Không nhét giá/tình trạng vào RAG — hai trường đó chỉ
có ở đây, tránh hai nguồn số liệu lệch nhau theo thời gian.

Trước đây tool này đọc thẳng CSV mỗi lần gọi (không có DB); giờ query SQL
thật. `inventory_units` là VIEW đọc thẳng `salemate_v1` (migration 005), nên
số liệu luôn khớp đúng thứ portal hiển thị — không còn bản sao để lệch.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.thuc_the import ma_can as ma_can_tu_thuc_the
from src.agents.tools.args import doc_tham_so
from src.agents.tools.registry import register_tool
from src.agents.tools.search import bo_ngu_canh_giao_dien, la_cau_hoi_dem
from src.agents.tools.trang_thai import nhan as nhan_trang_thai
from src.data.stores.inventory_db import get_inventory_db

# Mã căn: 2-4 chữ cái rồi 2-5 chữ số, ví dụ VOP345. Bao bằng \b để "VOP345"
# trong câu dài vẫn bắt được, còn "abcVOP345" thì không.
_UNIT_CODE = re.compile(r"\b([A-Za-z]{2,4}\d{2,5})\b")


def _extract_args(query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Rút mã căn từ câu hỏi. Không có mã thì trả None — tool không chạy.

    Cố ý CHỈ nhận mã căn, không đoán toà hay loại căn từ ngôn ngữ tự nhiên.
    Tra sai một căn rồi báo giá cho khách còn tệ hơn là không tra. Khi nào cần
    lọc theo toà/loại, thêm một tool riêng với schema rõ ràng.

    Từ HAI mã trở lên thì nhường `so_sanh_can`. Trước đây tool này vẫn chạy và
    bắt mã đầu tiên, nên "so sánh VOP619 với VOP893" chỉ tra được VOP619 rồi
    model từ chối vì thiếu căn kia. Chạy tiếp ở đây cũng chỉ nhồi thêm một bản
    sao của căn đầu vào prompt.
    """
    # Câu hỏi ĐẾM không nói về một căn. Mã căn duy nhất trong đó là do widget
    # chèn ("(căn đang xem: VOP758)"), nên tra nó chỉ nhồi một căn không liên
    # quan vào prompt — đúng thứ đã làm trợ lý trả lời "Ocean Park 3 còn bao
    # nhiêu căn?" bằng "căn đang xem là VOP758 thuộc Ocean Park 1".
    if la_cau_hoi_dem(query) and not _UNIT_CODE.search(bo_ngu_canh_giao_dien(query)):
        return None

    ma = [m.upper() for m in _UNIT_CODE.findall(query)]
    if not ma:
        # Câu không nêu mã ("căn đó còn không") thì lấy mã router đã giải tham
        # chiếu từ lịch sử. Vẫn giữ luật nhường nhau: đúng MỘT mã mới nhận.
        ma = ma_can_tu_thuc_the(entities)
    if len(ma) != 1:
        return None
    return {"unit_code": ma[0]}


class InventoryArgs(BaseModel):
    unit_code: str | None = Field(default=None, description="Mã căn cụ thể, ví dụ 'VOP398'")
    building: str | None = Field(default=None, description="Toà nhà, ví dụ 'R103'")
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN' (khớp gần đúng)")


def _to_row(record: dict[str, Any]) -> dict[str, Any]:
    return {**record, "status_label": nhan_trang_thai(record["status"])}


# LISTING và PRICE là hai nhãn mà câu hỏi về một căn cụ thể hay rơi vào. Khai
# rộng không sao: _extract_args mới là cửa quyết định, không có mã căn thì
# tool không chạy.
@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_extract_args)
class InventoryLookupTool(AgentTool):
    """Tra tình trạng căn hộ tồn kho thật theo mã căn / toà / loại căn."""

    name = "inventory_lookup"
    description = (
        "Tra tình trạng căn hộ THẬT theo thời gian thực (Còn / Đã đặt cọc / Đã bán), "
        "kèm giá — từ tồn kho nội bộ. Dùng khi người dùng hỏi còn căn nào trống, "
        "giá/tình trạng một căn cụ thể theo mã căn hoặc toà nhà."
    )
    args_schema = InventoryArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args, _ = doc_tham_so(InventoryArgs, kwargs)
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
