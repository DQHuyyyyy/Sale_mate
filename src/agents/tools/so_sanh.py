"""Tool so sánh nhiều căn — 2 đến 4 căn trong MỘT lượt tra.

Vì sao phải là tool riêng chứ không để `inventory_lookup` lo: `_extract_args`
của nó dùng `re.search`, tức chỉ bắt mã căn ĐẦU TIÊN. Câu "so sánh VOP619 với
VOP893" làm tool chạy với đúng VOP619, VOP893 không bao giờ được tra. Model có
một căn trong tay, thiếu căn kia, và từ chối trả lời — đúng nguyên tắc không
bịa, nhưng khách thì nhận một câu "chưa đủ dữ liệu" giữa lúc đang cân nhắc mua.

Ca đó từng được kỳ vọng là do vòng lặp agent lo (`plan` thấy thiếu thì gọi tool
lần nữa). Nhưng `ENABLE_AGENT_LOOP` mặc định TẮT và production không bật, nên
trên thực tế không có ai đi tra căn thứ hai. So sánh là việc người mua nhà làm
suốt — nó phải chạy được ở đường tất định, không phụ thuộc một cờ.

Trần 4 căn: bảng so sánh hiện trong khung chat hẹp, mỗi căn một cột. Quá 4 cột
là bảng phải cuộn ngang và không ai đọc nổi. Vượt trần thì lấy 4 căn đầu và NÓI
RÕ đã bỏ bớt, không im lặng cắt.
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
from src.agents.tools.trang_thai import nhan as nhan_trang_thai
from src.data.stores.inventory_db import get_inventory_db

_UNIT_CODE = re.compile(r"\b([A-Za-z]{2,4}\d{2,5})\b")

# Cố ý KHÔNG đòi có từ "so sánh": nêu từ hai mã căn trở lên đã là ý định đối
# chiếu rồi. "VOP619 và VOP893 cái nào tốt hơn" không chứa chữ nào trong danh
# sách từ khoá nào cả, mà rõ ràng là so sánh.
TOI_DA_CAN = 4

# Trường đem ra so sánh. Bỏ ảnh (model không dùng được) và hai cột số (bản số
# của price_label/area_m2, lặp lại) để bảng không phình.
_TRUONG_SO_SANH = (
    "unit_code",
    "subdivision",
    "building",
    "floor",
    "unit_type",
    "area_m2",
    "direction",
    "view",
    "price_label",
    "legal_status",
    "furniture",
)


def _rut_tham_so(query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Từ hai mã căn trở lên thì đây là việc so sánh, tool nhận.

    Một mã căn thì nhường `inventory_lookup` — nó tra một căn gọn hơn và câu
    trả lời không cần dựng bảng.

    Gộp thêm mã router giải tham chiếu từ lịch sử: "so sánh nó với VOP893" chỉ
    nêu MỘT mã trong câu, mã còn lại nằm ở lượt trước.
    """
    ma = list(dict.fromkeys([m.upper() for m in _UNIT_CODE.findall(query)] + ma_can_tu_thuc_the(entities)))
    if len(ma) < 2:
        return None
    return {"unit_codes": ma[:TOI_DA_CAN], "bo_bot": len(ma) - TOI_DA_CAN if len(ma) > TOI_DA_CAN else 0}


class SoSanhArgs(BaseModel):
    unit_codes: list[str] = Field(description=f"Danh sách 2-{TOI_DA_CAN} mã căn cần so sánh, ví dụ ['VOP345','VOP397']")
    bo_bot: int = Field(default=0, description="Số căn bị bỏ vì vượt trần, để báo lại cho người dùng")


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_rut_tham_so)
class SoSanhCanTool(AgentTool):
    """So sánh 2-4 căn hộ cạnh nhau theo giá, diện tích, hướng, view, pháp lý."""

    name = "so_sanh_can"
    description = (
        f"So sánh TỪ HAI ĐẾN {TOI_DA_CAN} căn hộ cạnh nhau: phân khu, diện tích, giá, hướng, view, "
        "pháp lý, nội thất, tình trạng. Dùng khi người dùng nêu nhiều mã căn và muốn đối chiếu, "
        "hỏi căn nào tốt hơn, hoặc khác nhau chỗ nào. Trả về dữ liệu THẬT của từng căn."
    )
    args_schema = SoSanhArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args, _ = doc_tham_so(SoSanhArgs, kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        ma = list(dict.fromkeys(m.strip().upper() for m in args.unit_codes if m and m.strip()))
        if len(ma) < 2:
            return ToolResult.failure("Cần ít nhất hai mã căn để so sánh.")

        try:
            rows = await asyncio.to_thread(get_inventory_db().query_units, unit_codes=ma[:TOI_DA_CAN])
        except Exception as exc:  # noqa: BLE001 - lỗi DB không được làm đứt luồng agent
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        return ToolResult(ok=True, data=_ket_qua(ma[:TOI_DA_CAN], rows, args.bo_bot), source="inventory:postgres")


def _ket_qua(da_hoi: list[str], rows: list[dict[str, Any]], bo_bot: int) -> dict[str, Any]:
    """Gói kết quả, nêu RÕ căn nào không tìm thấy.

    Im lặng bỏ căn không có là để model tự suy diễn — nó sẽ so sánh hai căn rồi
    lờ căn thứ ba đi như thể người dùng chưa từng hỏi.
    """
    theo_ma = {str(r.get("unit_code", "")).upper(): r for r in rows}
    tim_thay = [_gon(theo_ma[m]) for m in da_hoi if m in theo_ma]
    khong_thay = [m for m in da_hoi if m not in theo_ma]

    data: dict[str, Any] = {"so_can": len(tim_thay), "can": tim_thay}
    if khong_thay:
        data["khong_tim_thay"] = khong_thay
        data["luu_y"] = f"Không có căn {', '.join(khong_thay)} trong tồn kho. Nói rõ điều này, đừng bỏ qua."
    if bo_bot > 0:
        data["bo_bot"] = bo_bot
        data["luu_y_tran"] = f"Người dùng nêu nhiều hơn {TOI_DA_CAN} căn; đã bỏ {bo_bot} căn cuối. Nói rõ."
    return data


def _gon(row: dict[str, Any]) -> dict[str, Any]:
    """Bản rút gọn của một căn, kèm nhãn tình trạng đọc được."""
    gon = {k: row[k] for k in _TRUONG_SO_SANH if k in row}
    trang_thai = row.get("status")
    if trang_thai:
        gon["status_label"] = nhan_trang_thai(trang_thai)
    return gon
