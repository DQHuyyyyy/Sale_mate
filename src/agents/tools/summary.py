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
from src.agents.thuc_the import tieu_chi_tim
from src.agents.tools import trang_thai as tt
from src.agents.tools.registry import register_tool
from src.agents.tools.search import bo_ngu_canh_giao_dien, chuan_hoa, doc_phan_khu
from src.data.stores.inventory_db import get_inventory_db

_CON_HANG = tt.CON

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


def _extract_args(query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Chỉ chạy với câu hỏi tổng hợp, và không có mã căn cụ thể.

    Có mã căn nghĩa là người dùng hỏi về đúng căn đó — việc của
    `inventory_lookup`, không phải đếm cả kho.
    """
    # Đuôi "(căn đang xem: VOP758)" do widget chèn KHÔNG phải lời người dùng —
    # bỏ trước khi soi mã căn, nếu không thì mọi câu đếm hỏi trong lúc đang mở
    # một căn đều bị tool này bỏ qua. Xem `bo_ngu_canh_giao_dien`.
    query = bo_ngu_canh_giao_dien(query)
    thap = query.lower()
    if _MA_CAN.search(query):
        return None
    if not any(dau in thap for dau in _DAU_HIEU):
        return None

    # Người dùng nêu phân khu thì PHẢI đếm trong phân khu đó. Thiếu vế này, tool
    # trả con số toàn kho nằm cạnh con số đã lọc của `inventory_search`, và model
    # chọn nhầm — đo được: "phân khu 3 còn bao nhiêu căn" trả lời 97 thay vì 30.
    # Câu hiện tại thắng; thiếu thì lấy phân khu đang bàn ở lượt trước, để
    # "vậy còn bao nhiêu căn" đếm đúng phân khu chứ không đếm cả kho.
    phan_khu = doc_phan_khu(query) or tieu_chi_tim(entities).get("subdivision")
    return {"subdivision": phan_khu} if phan_khu else {}


def _pham_vi(args: SummaryArgs) -> dict[str, str]:
    """Bộ lọc THẬT SỰ đã áp dụng, để trả ngược lại cho model."""
    return {
        k: v
        for k, v in (("subdivision", args.subdivision), ("building", args.building), ("unit_type", args.unit_type))
        if v
    }


def _mo_ta(pham_vi: dict[str, str]) -> str:
    """Phạm vi viết thành lời, để model chép thẳng vào câu trả lời."""
    if not pham_vi:
        return "toàn bộ tồn kho"
    nhan = {"subdivision": "phân khu", "building": "toà", "unit_type": "loại căn"}
    return ", ".join(f"{nhan[k]} {v}" for k, v in pham_vi.items())


class SummaryArgs(BaseModel):
    building: str | None = Field(default=None, description="Chỉ đếm trong một toà, ví dụ 'S210'")
    unit_type: str | None = Field(default=None, description="Chỉ đếm một loại căn, ví dụ '2PN'")
    subdivision: str | None = Field(
        default=None, description="Chỉ đếm một phân khu: 'Ocean Park 1', 'Ocean Park 2' hoặc 'Ocean Park 3'"
    )


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_extract_args)
class InventorySummaryTool(AgentTool):
    """Thống kê tồn kho theo số lượng."""

    name = "inventory_summary"
    # Nhãn hiện trên dòng "Nguồn" — kết quả là con số tổng hợp nên không có mã
    # căn nào để trỏ vào. Xem `_nguon_cua_tool`.
    nhan_nguon = "Dữ liệu tồn kho"
    description = (
        "Đếm số căn theo tình trạng (đang bán / đã đặt cọc / đã bán) trong tồn kho, "
        "tổng hợp theo toà và loại căn. Kết quả kèm `pham_vi` cho biết đã đếm trong phạm vi nào. "
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
            if args.subdivision:
                wanted = chuan_hoa(args.subdivision)
                records = [r for r in records if chuan_hoa(str(r.get("subdivision") or "")) == wanted]
        except Exception as exc:  # noqa: BLE001 - lỗi kết nối DB, không làm đứt luồng
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        pham_vi = _pham_vi(args)
        if not records:
            return ToolResult(
                ok=True,
                data={"pham_vi": pham_vi},
                source="inventory:postgres",
                error=f"Không có căn nào khớp điều kiện ({_mo_ta(pham_vi)}).",
            )

        return ToolResult(ok=True, data=self._thong_ke(records, pham_vi), source="inventory:postgres")

    @staticmethod
    def _thong_ke(records: list[dict[str, Any]], pham_vi: dict[str, str]) -> dict[str, Any]:
        # Ba nhóm rời nhau. Bản cũ tính `da_ban = tổng − còn trống`, đúng khi
        # chỉ có hai trạng thái nhưng gộp thẳng "đã đặt cọc" vào "đã bán" ngay
        # khi có trạng thái thứ ba — báo cho sale rằng căn đã mất trong khi cọc
        # còn có thể huỷ.
        nhom = Counter(str(r.get("status") or "") for r in records)
        con = [r for r in records if r.get("status") == _CON_HANG]
        return {
            # ⚠️ PHẢI trả lại phạm vi đã lọc. Bản đầu chỉ trả con số trần, và
            # model không có cách nào biết nó đếm phân khu nào — hỏi "Ocean Park
            # 3 còn bao nhiêu căn đang bán?" thì tool lọc đúng OP3 rồi, nhưng
            # trợ lý vẫn trả lời "ngữ cảnh chỉ cho biết tồn kho có 30 căn còn
            # trống, chưa xác định số đó thuộc Ocean Park 3 hay phân khu khác".
            # Nó cầm đúng câu trả lời trong tay mà không dám đưa — và đúng ra là
            # không dám thật, vì thiếu vế phạm vi thì khẳng định là đoán.
            #
            # Luật chung: tool nào LỌC rồi trả số TỔNG HỢP đều phải echo bộ lọc.
            "pham_vi": pham_vi,
            "mo_ta_pham_vi": _mo_ta(pham_vi),
            "tong_so_can": len(records),
            # "đang bán" và "còn trống" là MỘT — đặt tên theo vế người mua hay
            # hỏi ("còn bao nhiêu căn đang bán") để model không phải bắc cầu.
            "dang_ban": len(con),
            "da_dat_coc": nhom[tt.DA_DAT_COC],
            "da_ban": nhom[tt.DA_BAN],
            # Chỉ thống kê phần ĐANG BÁN theo toà/loại: sale cần biết còn gì để
            # chào khách, không cần phân bố của những căn đã bán.
            "dang_ban_theo_toa": dict(sorted(Counter(r.get("building") for r in con).items())),
            "dang_ban_theo_loai": dict(sorted(Counter(r.get("unit_type") for r in con).items())),
        }
