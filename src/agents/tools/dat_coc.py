"""Tool đặt cọc — bước chốt của cả luồng tư vấn.

Khách xem căn, so sánh, tính khoản vay… rồi để lại tên và số điện thoại. Tool
này ghi lead vào Postgres để đội sale gọi lại. Không có nó thì mọi gợi ý dẫn
tới "đặt cọc" đều là nút bấm rỗng.

**Tool chạy ngay cả khi khách CHƯA cho số điện thoại.** Đó là chủ ý, không phải
thiếu kiểm tra: câu "đặt cọc căn VOP397" phải được nhận thì trợ lý mới có cớ
hỏi xin số. Nếu đòi đủ số mới chạy thì câu đó rơi vào nhánh "chưa đủ dữ liệu",
khách bị từ chối ngay đúng lúc họ muốn mua — và bộ lọc gợi ý cũng loại luôn nút
"Đặt cọc" vì không tool nào nhận. Thiếu thông tin thì tool trả về danh sách
trường còn thiếu để `generate` hỏi xin, đủ thì mới ghi.

Không bịa điều khoản: tool chỉ ghi nhận nhu cầu và hẹn sale gọi lại. Số tiền
cọc, thời hạn giữ chỗ, chính sách phạt — không có trong dữ liệu nào của hệ
thống, nên trợ lý không được phép nói.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.tools.args import doc_tham_so
from src.agents.tools.registry import register_tool
from src.data.stores.dat_coc_db import get_dat_coc_db

_UNIT_CODE = re.compile(r"\b([A-Za-z]{2,4}\d{2,5})\b")

# Ý định chốt. "cọc" đứng riêng phải có ranh giới từ, nếu không "cọc" trong
# "cột mốc" hay tên riêng cũng khớp.
_Y_DINH_COC = re.compile(
    r"đặt\s*cọc|dat\s*coc|\bcọc\b|giữ\s*chỗ|giu\s*cho|book\b|đăng\s*ký\s*mua|"
    r"chốt\s*căn|mua\s*căn\s*này|xuống\s*tiền",
    re.IGNORECASE,
)

# Số điện thoại Việt Nam: 0xxxxxxxxx hoặc +84xxxxxxxxx, cho phép . - khoảng
# trắng xen giữa vì người ta gõ "0912 345 678".
_SDT = re.compile(r"(?:\+?84|0)(?:[\s.\-]?\d){9}")

# "tên tôi là Nam", "tôi tên Nguyễn Văn A", "mình là Hoa". Chỉ nhận khi có từ
# dẫn rõ ràng — đoán tên từ câu tự do là cách nhanh nhất để ghi sai tên khách.
_HO_TEN = re.compile(
    r"(?:tên\s+(?:tôi|mình|em|anh|chị)\s+là|(?:tôi|mình|em|anh|chị)\s+tên(?:\s+là)?|tên\s*:)\s*"
    r"([A-Za-zÀ-ỹ][A-Za-zÀ-ỹ\s]{1,40}?)(?=\s*[,.;]|\s+(?:số|sđt|điện thoại|liên hệ)|$)",
    re.IGNORECASE,
)


def chuan_hoa_sdt(thô: str) -> str:
    """Bỏ mọi ký tự ngăn cách, quy +84 về 0 — để so trùng không lệch định dạng."""
    so = re.sub(r"[^\d+]", "", thô)
    if so.startswith("+84"):
        return "0" + so[3:]
    if so.startswith("84") and len(so) == 11:
        return "0" + so[2:]
    return so


def _rut_tham_so(query: str) -> dict[str, Any] | None:
    """Có ý định cọc và có mã căn thì tool chạy. Tên và số lấy được thì lấy.

    Không đòi đủ số điện thoại ở đây — xem docstring đầu file.
    """
    if not _Y_DINH_COC.search(query):
        return None
    ma = _UNIT_CODE.search(query)
    if ma is None:
        return None

    args: dict[str, Any] = {"unit_code": ma.group(1).upper()}

    sdt = _SDT.search(query)
    if sdt is not None:
        args["so_dien_thoai"] = chuan_hoa_sdt(sdt.group(0))

    ten = _HO_TEN.search(query)
    if ten is not None:
        args["ho_ten"] = " ".join(ten.group(1).split())

    return args


class DatCocArgs(BaseModel):
    unit_code: str = Field(description="Mã căn khách muốn cọc, ví dụ 'VOP397'")
    so_dien_thoai: str | None = Field(default=None, description="Số điện thoại khách để lại")
    ho_ten: str | None = Field(default=None, description="Họ tên khách, nếu khách đã nói")
    ghi_chu: str | None = Field(default=None, description="Yêu cầu thêm của khách, nếu có")


@register_tool(intents={Intent.LISTING, Intent.PRICE}, build_args=_rut_tham_so)
class DatCocTool(AgentTool):
    """Ghi nhận nhu cầu đặt cọc một căn và lưu thông tin liên hệ của khách."""

    name = "dat_coc"
    description = (
        "Ghi nhận khách muốn ĐẶT CỌC / GIỮ CHỖ một căn cụ thể và lưu lại họ tên, số điện "
        "thoại để đội sale gọi lại chốt. Dùng khi khách nói muốn cọc, giữ chỗ, chốt căn "
        "hoặc đăng ký mua. Thiếu số điện thoại thì tool báo lại để hỏi xin, không tự bịa."
    )
    args_schema = DatCocArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args, _ = doc_tham_so(DatCocArgs, kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        sdt = chuan_hoa_sdt(args.so_dien_thoai or "")
        if not _hop_le_sdt(sdt):
            return ToolResult(
                ok=True,
                data=_con_thieu(args, sdt),
                source="dat_coc:postgres",
            )

        try:
            return await asyncio.to_thread(self._ghi, args, sdt)
        except Exception as exc:  # noqa: BLE001 - lỗi DB không được làm đứt luồng agent
            return ToolResult.failure(f"Chưa lưu được yêu cầu đặt cọc: {exc}")

    def _ghi(self, args: DatCocArgs, sdt: str) -> ToolResult:
        db = get_dat_coc_db()
        ma_can = args.unit_code.upper()

        if db.da_co_hom_nay(ma_can, sdt):
            return ToolResult(
                ok=True,
                data={
                    "trang_thai": "da_ghi_nhan_truoc_do",
                    "ma_can": ma_can,
                    "loi_nhan": "Yêu cầu giữ chỗ căn này đã được ghi nhận hôm nay, đội sale sẽ liên hệ.",
                },
                source="dat_coc:postgres",
            )

        ma_lead = db.ghi_lead(
            ma_can=ma_can,
            so_dien_thoai=sdt,
            ho_ten=(args.ho_ten or "").strip(),
            ghi_chu=(args.ghi_chu or "").strip(),
        )
        return ToolResult(
            ok=True,
            data={
                "trang_thai": "da_ghi_nhan",
                "ma_lead": ma_lead,
                "ma_can": ma_can,
                "ho_ten": (args.ho_ten or "").strip(),
                # Số điện thoại KHÔNG trả lại vào ngữ cảnh model: nó sẽ nằm
                # trong prompt rồi đi vào log của nhà cung cấp LLM. Khách vừa
                # gõ số đó nên không cần đọc lại cho họ nghe.
                "loi_nhan": "Đã ghi nhận yêu cầu giữ chỗ, đội sale sẽ liên hệ trong thời gian sớm nhất.",
            },
            source="dat_coc:postgres",
        )


def _hop_le_sdt(so: str) -> bool:
    """Số di động Việt Nam sau chuẩn hoá: 0 + 9 chữ số."""
    return bool(re.fullmatch(r"0\d{9}", so))


def _con_thieu(args: DatCocArgs, sdt: str) -> dict[str, Any]:
    """Báo cho model biết còn thiếu gì để nó hỏi xin đúng thứ đó."""
    thieu = ["số điện thoại"] if not _hop_le_sdt(sdt) else []
    if not (args.ho_ten or "").strip():
        thieu.append("họ tên")
    return {
        "trang_thai": "can_bo_sung",
        "ma_can": args.unit_code.upper(),
        "con_thieu": thieu,
        "loi_nhan": (
            "Chưa lưu được yêu cầu giữ chỗ. Hỏi khách cung cấp "
            + " và ".join(thieu)
            + ", KHÔNG tự bịa. Không nêu số tiền cọc hay thời hạn giữ chỗ vì hệ thống chưa có dữ liệu đó."
        ),
    }
