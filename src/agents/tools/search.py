"""Tool tìm căn theo tiêu chí — bổ sung cho `inventory_lookup` tra theo mã căn.

Hai tool loại trừ nhau tự nhiên: `inventory_lookup` cần mã căn, tool này cần
tiêu chí. Câu có mã căn thì tool này im lặng, để tool kia trả lời chính xác một
căn thay vì trả về một danh sách.

KHÔNG hardcode danh sách toà nhà hay loại căn. Từ vựng lọc đọc từ chính SQL:
thêm toà mới vào dữ liệu là tool nhận ra ngay, không ai phải sửa code. Đây cũng
là cách duy nhất không bỏ sót khi dữ liệu ghi không thống nhất — trước đây cột
loại căn có 10 cách viết cho 6 loại, hardcode '%2PN%' sẽ mất sạch những căn ghi
'2 PN'. Chuẩn hoá cả hai vế trước khi so là xong.

Phần duy nhất là luật ngôn ngữ, không phải dữ liệu: "phòng ngủ" -> "PN" và
"view X" -> tìm X trong cột View. Ánh xạ tiếng Việt sang tên cột thì không
tránh được, nhưng giữ ở mức tối thiểu.
"""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.tools.registry import register_tool
from src.core.logging import get_logger
from src.data.stores.inventory_db import get_inventory_db

logger = get_logger(__name__)

# Trần số căn đưa vào prompt. Trả 41 căn 1PN vào context chỉ tổ đẩy model ra xa
# câu hỏi; nói rõ tổng số rồi liệt kê vài căn thì hữu ích hơn.
MAX_RESULTS = 8

# Từ vựng đọc từ SQL nên phải làm mới, nhưng không phải mỗi lượt hỏi.
_VOCAB_TTL_S = 300.0

_UNIT_CODE = re.compile(r"\b[A-Za-z]{2,4}\d{2,5}\b")
# "2 phòng ngủ", "2pn", "2 PN" — số phòng ngủ là tiêu chí hay được hỏi nhất.
_BEDROOMS = re.compile(r"(\d)\s*(?:phòng\s*ngủ|pn\b)", re.IGNORECASE)
# "view biển", "view hồ" — lấy ĐÚNG MỘT từ ngay sau chữ "view".
# Lấy hai từ thì "view hồ tòa R103" thành từ khoá "hồ tòa" và không khớp gì cả.
# Một từ có thể rộng hơn ý người hỏi, nhưng rộng còn trả về căn thật; sai thì
# trả rỗng và người dùng không hiểu vì sao.
_VIEW = re.compile(r"view\s+([^\s,.]+)", re.IGNORECASE)


def _fold(text: str) -> str:
    """Bỏ dấu tiếng Việt, bỏ mọi khoảng trắng và dấu câu, viết hoa.

    Nhờ vậy '2 PN, 1WC' và '2PN,1WC' và '2pn 1wc' đều thành '2PN1WC'.
    """
    no_mark = unicodedata.normalize("NFD", text)
    no_mark = "".join(ch for ch in no_mark if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^0-9A-Za-z]", "", no_mark).upper()


class _Vocabulary:
    """Giá trị hợp lệ của từng cột, đọc từ SQL và nhớ tạm theo TTL."""

    def __init__(self) -> None:
        self._values: dict[str, list[str]] = {}
        self._loaded_at = 0.0

    def get(self) -> dict[str, list[str]]:
        if not self._values or time.monotonic() - self._loaded_at > _VOCAB_TTL_S:
            self._reload()
        return self._values

    def _reload(self) -> None:
        rows = get_inventory_db().query_units()
        self._values = {
            field: sorted({str(r[field]) for r in rows if r.get(field)})
            for field in ("unit_type", "building", "direction")
        }
        self._loaded_at = time.monotonic()
        logger.info(
            "Nạp từ vựng lọc từ SQL: %s",
            {k: len(v) for k, v in self._values.items()},
        )

    def clear(self) -> None:
        self._values = {}
        self._loaded_at = 0.0


vocabulary = _Vocabulary()


def _match_unit_type(query: str, values: list[str]) -> str | None:
    """Khớp loại căn: ưu tiên số phòng ngủ, sau đó tên gọi thẳng (Studio)."""
    match = _BEDROOMS.search(query)
    if match:
        wanted = f"{match.group(1)}PN"
        # Trả giá trị THẬT trong DB, không trả chuỗi tự chế.
        hits = [v for v in values if _fold(v).startswith(wanted)]
        return hits[0] if len(hits) == 1 else (wanted if hits else None)

    folded = _fold(query)
    for value in values:
        if _fold(value) in folded:
            return value
    return None


def _match_building(query: str, values: list[str]) -> str | None:
    """Khớp toà nhà theo TỪ RIÊNG, không phải chuỗi con.

    Có mã toà chỉ hai ký tự ('S1', 'H2', 'P3'), khớp chuỗi con sẽ bắt nhầm khi
    chúng nằm lọt giữa một từ khác. So theo token thì 'S210' trong câu chỉ khớp
    toà S210, không khớp S2.
    """
    tokens = {_fold(t) for t in re.split(r"[^0-9A-Za-zÀ-ỹ]+", query) if t}
    by_value = {_fold(v): v for v in values}
    for token in sorted(tokens, key=len, reverse=True):
        if token in by_value:
            return by_value[token]
    return None


def _match_direction(query: str, values: list[str]) -> str | None:
    """Khớp hướng — giá trị nhiều từ nên phải so chuỗi con, không so token.

    Xét giá trị dài trước: 'Đông Bắc - Đông Nam' cụ thể hơn 'Đông Nam'.
    """
    folded = _fold(query)
    for value in sorted(values, key=len, reverse=True):
        if _fold(value) and _fold(value) in folded:
            return value
    return None


def extract_criteria(query: str) -> dict[str, Any] | None:
    """Rút tiêu chí lọc từ câu hỏi. Trả None nghĩa là tool không nên chạy."""
    if _UNIT_CODE.search(query):
        return None  # Có mã căn -> việc của inventory_lookup

    values = vocabulary.get()
    criteria: dict[str, Any] = {}

    unit_type = _match_unit_type(query, values.get("unit_type", []))
    if unit_type:
        criteria["unit_type"] = unit_type

    building = _match_building(query, values.get("building", []))
    if building:
        criteria["building"] = building

    direction = _match_direction(query, values.get("direction", []))
    if direction:
        criteria["direction"] = direction

    view = _VIEW.search(query)
    if view:
        criteria["view_keyword"] = view.group(1).strip()

    return criteria or None


class SearchArgs(BaseModel):
    unit_type: str | None = Field(default=None, description="Loại căn, ví dụ '2PN' hoặc 'Studio'")
    building: str | None = Field(default=None, description="Toà nhà, ví dụ 'S210'")
    direction: str | None = Field(default=None, description="Hướng, ví dụ 'Đông Nam'")
    view_keyword: str | None = Field(default=None, description="Từ khoá trong mô tả view, ví dụ 'biển'")


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=extract_criteria)
class InventorySearchTool(AgentTool):
    """Tìm căn còn bán theo tiêu chí."""

    name = "inventory_search"
    description = (
        "Tìm danh sách căn hộ CÒN BÁN theo tiêu chí: số phòng ngủ, toà nhà, hướng, view. "
        "Dùng khi người dùng mô tả căn muốn tìm mà không nêu mã căn cụ thể."
    )
    args_schema = SearchArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args = SearchArgs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        try:
            # CHỈ đẩy `building` xuống SQL. Loại căn lọc ở Python bằng _fold:
            # `query_units` dùng ILIKE nên '%2PN%' bỏ sót căn ghi '2 PN, 1WC'.
            # Dữ liệu hiện đã chuẩn hoá, nhưng tool không được phụ thuộc vào
            # việc dữ liệu mãi mãi sạch — bỏ sót căn là hỏng câm, không báo lỗi.
            rows = await asyncio.to_thread(
                get_inventory_db().query_units,
                building=args.building,
            )
        except Exception as exc:  # noqa: BLE001 - lỗi DB, không làm đứt luồng agent
            return ToolResult.failure(f"Không truy vấn được cơ sở dữ liệu tồn kho: {exc}")

        rows = self._filter(rows, args)
        if not rows:
            return ToolResult(
                ok=True,
                data=[],
                source="inventory:postgres",
                error="Không có căn nào còn bán khớp tiêu chí.",
            )

        return ToolResult(
            ok=True,
            data={"tong_so_khop": len(rows), "danh_sach": rows[:MAX_RESULTS]},
            source="inventory:postgres",
        )

    def _filter(self, rows: list[dict[str, Any]], args: SearchArgs) -> list[dict[str, Any]]:
        """Lọc mọi tiêu chí trừ toà nhà, dùng chung một phép so đã chuẩn hoá.

        Gom về một chỗ để không có hai luật khớp khác nhau (SQL một kiểu, Python
        một kiểu) rồi lệch nhau lúc dữ liệu ghi không thống nhất.
        """
        result = [r for r in rows if r.get("status") == "available"]

        if args.unit_type:
            wanted = _fold(args.unit_type)
            result = [r for r in result if _fold(str(r.get("unit_type") or "")).startswith(wanted)]

        if args.direction:
            wanted = _fold(args.direction)
            result = [r for r in result if wanted in _fold(str(r.get("direction") or ""))]

        if args.view_keyword:
            wanted = _fold(args.view_keyword)
            result = [r for r in result if wanted in _fold(str(r.get("view") or ""))]

        return result
