"""Tool tính khoản vay mua căn, có đối chiếu chính sách hỗ trợ lãi suất.

Vì sao cần tool thay vì để model tự nhẩm: đã đo được model bịa. Hỏi "tôi có 1
tỷ, mua căn VOP397 thì vay thế nào", nó lấy đúng giá từ tool tồn kho rồi tự
thêm "ngân hàng cho vay lên đến 70-80% giá trị" — con số không có trong tài
liệu nào. Nghe rất thuyết phục và không ai kiểm được.

Ba thứ tool này TỪ CHỐI đoán, vì cả ba đều là chỗ model vừa bịa:

1. Lãi suất khi không có chính sách nào còn hiệu lực.
2. Lãi suất sau khi hết giai đoạn khoá trần — lúc đó thả nổi theo ngân hàng.
3. Tỷ lệ cho vay mà ngân hàng sẽ duyệt — chính sách chỉ nói mức được HỖ TRỢ.

Mọi con số trả về đều truy được về `data/chinh_sach_vay.json` (tham số chính
sách) hoặc `inventory_units` (giá căn). Không có số nào sinh ra ở đây.

Đơn vị tiền thống nhất là TỶ ĐỒNG, giống `price_value` trong tồn kho và giống
`_doc_tien` của tool tìm kiếm — đổi đơn vị giữa chừng là nguồn sai số kinh điển.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.agents.contracts import AgentTool, ToolResult
from src.agents.state import Intent
from src.agents.thuc_the import ma_can as ma_can_tu_thuc_the
from src.agents.tools.args import doc_tham_so
from src.agents.tools.chinh_sach_vay import (
    ChinhSachVay,
    chinh_sach_dang_ap_dung,
    chinh_sach_gan_nhat_da_het,
)
from src.agents.tools.registry import register_tool
from src.agents.tools.search import _TIEN, _doc_tien
from src.data.stores.inventory_db import get_inventory_db

_UNIT_CODE = re.compile(r"\b([A-Za-z]{2,4}\d{2,5})\b")

# Số tiền NGƯỜI DÙNG ĐANG CÓ. Phải bám từ chỉ sở hữu, không lấy bừa con số đầu
# tiên: "tôi có 1 tỷ, tìm căn dưới 3 tỷ" có hai số và chỉ số đầu là vốn.
_VON_TU_CO = re.compile(
    rf"(?:có|sẵn|vốn|trong tay|tích lu[ỹy]|dành dụm|tiết kiệm)\s*(?:khoảng\s*)?{_TIEN}",
    re.IGNORECASE,
)

# Câu hỏi nhắc tới chuyện vay mượn. Dùng để tool im khi người dùng chỉ khoe vốn
# mà không hỏi vay ("tôi có 2 tỷ, còn căn nào không" là việc của inventory_search).
_Y_DINH_VAY = re.compile(
    r"vay|trả góp|tra gop|lãi suất|lai suat|khoản vay|khoan vay|ngân hàng|ngan hang|hỗ trợ tài chính",
    re.IGNORECASE,
)


def _rut_tham_so(query: str, entities: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Rút mã căn + vốn tự có. Thiếu một trong hai thì tool không chạy.

    Cần CẢ HAI mới đủ để tính: biết vốn mà không biết mua căn nào thì không có
    giá để trừ, biết căn mà không biết vốn thì không biết vay bao nhiêu.

    Cả hai đều lấy được từ lịch sử — "có 1 tỷ thì vay căn đó thế nào" nêu vốn
    mà không nêu mã. Riêng Ý ĐỊNH VAY luôn đọc câu hiện tại: kế thừa ý định là
    chạy một tool người dùng không hề yêu cầu ở lượt này.
    """
    # Xét ý định TRƯỚC: không hỏi vay thì để tool khác trả lời, khỏi mất công rút.
    if not _Y_DINH_VAY.search(query):
        return None

    khop_ma = _UNIT_CODE.search(query)
    ma = khop_ma.group(1).upper() if khop_ma else next(iter(ma_can_tu_thuc_the(entities)), None)
    if ma is None:
        return None

    von = _VON_TU_CO.search(query)
    so_tien = _doc_tien(von.group(1), von.group(2)) if von else (entities or {}).get("von_tu_co")
    if so_tien is None or so_tien <= 0:
        return None

    return {"unit_code": ma, "von_tu_co": float(so_tien)}


def _nguon_chinh_sach() -> str:
    """`doc_id` của tài liệu chính sách đã dùng để tính — để trích ngược về được.

    Mọi con số định lượng của tool này (trần lãi suất, các gói 18/24/30/36/60
    tháng, phụ phí theo tỷ lệ vay) đến từ `chinh_sach_vay.json`, mà file đó khai
    sẵn `doc_id` trỏ về tài liệu văn bản gốc — chính là để câu trả lời trích
    ngược. Trước đây tool trả `source="tool:tinh_khoan_vay"` nên dòng "Nguồn"
    hiện một cái tên máy, bấm vào không ra gì.

    Lấy cả chính sách ĐÃ HẾT HẠN: khi hết hiệu lực, tool vẫn nói "chính sách
    6%/năm đã hết hạn từ 20/07/2026" — đó cũng là một khẳng định lấy từ tài
    liệu, và người đọc có quyền kiểm.

    Không có chính sách nào trong file thì rơi về tên tool, còn hơn không nguồn.
    """
    hom_nay = date.today()
    cs = chinh_sach_dang_ap_dung(hom_nay) or chinh_sach_gan_nhat_da_het(hom_nay)
    return (cs.doc_id if cs and cs.doc_id else "") or "tool:tinh_khoan_vay"


class KhoanVayArgs(BaseModel):
    unit_code: str | None = Field(default=None, description="Mã căn muốn mua, ví dụ 'VOP397'")
    gia_can: float | None = Field(default=None, description="Giá căn tính bằng TỶ đồng, khi đã biết sẵn")
    von_tu_co: float = Field(description="Số tiền người mua đang có, tính bằng TỶ đồng")
    ky_han_vay_nam: int | None = Field(default=None, description="Kỳ hạn vay muốn tính, tính bằng năm")


def _tra_hang_thang(no_goc: float, lai_suat_nam: float, so_thang: int) -> float:
    """Trả góp đều hàng tháng theo công thức niên kim.

    Lãi suất 0 thì công thức niên kim chia cho 0 — tách nhánh, đừng để nó nổ
    giữa lúc trả lời khách.
    """
    if so_thang <= 0:
        return 0.0
    lai_thang = lai_suat_nam / 100 / 12
    if lai_thang == 0:
        return no_goc / so_thang
    he_so = (1 + lai_thang) ** -so_thang
    return no_goc * lai_thang / (1 - he_so)


def _cac_goi(chinh_sach: ChinhSachVay, muc_vay: int, gia: float) -> list[dict[str, Any]]:
    """Các gói hỗ trợ ở mức vay này, kèm phụ phí quy ra tiền.

    `phu_phi` là phần trăm cộng vào GIÁ, không phải lãi suất — nêu cả số tiền
    để người đọc không phải tự nhân.
    """
    ket_qua = []
    for goi in chinh_sach.goi:
        phan_tram = goi.phu_phi_theo_muc_vay(muc_vay)
        if phan_tram is None:
            continue
        ket_qua.append(
            {
                "so_thang_ho_tro": goi.so_thang,
                "mien_lai_hoan_toan": goi.mien_lai,
                "phu_phi_phan_tram": phan_tram,
                "phu_phi_ty": round(gia * phan_tram / 100, 3),
                "gia_sau_phu_phi_ty": round(gia * (1 + phan_tram / 100), 3),
                "duoc_tiep_suc_sau_uu_dai": (
                    goi.so_thang <= chinh_sach.goi_duoc_tiep_suc_toi_da_thang and chinh_sach.tran_sau_uu_dai is not None
                ),
            }
        )
    return ket_qua


@register_tool(
    intents={Intent.PRICE, Intent.LISTING, Intent.LEGAL, Intent.DOCUMENT},
    build_args=_rut_tham_so,
)
class TinhKhoanVayTool(AgentTool):
    """Tính khoản vay cần thiết và đối chiếu chính sách hỗ trợ lãi suất."""

    name = "tinh_khoan_vay"
    description = (
        "Tính số tiền cần vay khi mua một căn cụ thể với số vốn sẵn có, kèm trả góp hàng tháng "
        "và chính sách hỗ trợ lãi suất ĐANG CÒN HIỆU LỰC (nếu có). Dùng khi người dùng nêu số "
        "tiền họ đang có và hỏi vay bao nhiêu, trả góp thế nào, có hỗ trợ lãi suất gì không."
    )
    args_schema = KhoanVayArgs

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            args, _ = doc_tham_so(KhoanVayArgs, kwargs)
        except Exception as exc:  # noqa: BLE001 - trả lỗi cho agent, không làm đứt luồng
            return ToolResult.failure(f"Tham số không hợp lệ: {exc}")

        gia, loi = await self._lay_gia(args)
        if gia is None:
            return ToolResult.failure(loi)

        if args.von_tu_co >= gia:
            return ToolResult(
                ok=True,
                data={
                    "gia_can_ty": gia,
                    "von_tu_co_ty": args.von_tu_co,
                    "can_vay_ty": 0,
                    "ghi_chu": "Vốn tự có đã đủ mua căn này, không cần vay.",
                },
                source="tool:tinh_khoan_vay",
            )

        return ToolResult(ok=True, data=self._tinh(args, gia), source=_nguon_chinh_sach())

    async def _lay_gia(self, args: KhoanVayArgs) -> tuple[float | None, str]:
        """Giá căn: ưu tiên tồn kho thật, chỉ dùng `gia_can` khi không có mã căn."""
        if args.unit_code:
            try:
                records = await asyncio.to_thread(get_inventory_db().query_units, unit_code=args.unit_code)
            except Exception as exc:  # noqa: BLE001 - lỗi DB không được làm đứt luồng agent
                return None, f"Không truy vấn được tồn kho: {exc}"

            if not records:
                return None, f"Không tìm thấy căn {args.unit_code} trong tồn kho."

            gia = records[0].get("price_value")
            if gia is None:
                return None, f"Căn {args.unit_code} chưa có giá trong tồn kho nên chưa tính được khoản vay."
            return float(gia), ""

        if args.gia_can and args.gia_can > 0:
            return float(args.gia_can), ""

        return None, "Cần mã căn hoặc giá căn để tính khoản vay."

    def _tinh(self, args: KhoanVayArgs, gia: float) -> dict[str, Any]:  # noqa: D102
        can_vay = gia - args.von_tu_co
        ty_le_vay = can_vay / gia * 100

        ket_qua: dict[str, Any] = {
            "ma_can": args.unit_code or "",
            "gia_can_ty": round(gia, 3),
            "von_tu_co_ty": round(args.von_tu_co, 3),
            "can_vay_ty": round(can_vay, 3),
            "ty_le_vay_phan_tram": round(ty_le_vay, 1),
        }

        hom_nay = date.today()
        chinh_sach = chinh_sach_dang_ap_dung(hom_nay)
        if chinh_sach is None:
            ket_qua.update(self._khi_khong_co_chinh_sach(hom_nay))
            return ket_qua

        ket_qua.update(self._theo_chinh_sach(chinh_sach, args, can_vay, ty_le_vay, gia))
        return ket_qua

    @staticmethod
    def _khi_khong_co_chinh_sach(hom_nay: date) -> dict[str, Any]:
        """Không có chính sách hiệu lực — nói thẳng, KHÔNG mượn lãi suất cũ.

        Đây là chỗ dễ sai nhất: rơi về chính sách gần nhất trông thì "hữu ích"
        nhưng là báo cho khách một ưu đãi họ không được hưởng.
        """
        da_het = chinh_sach_gan_nhat_da_het(hom_nay)
        thong_tin: dict[str, Any] = {
            "chinh_sach_ho_tro_lai_suat": None,
            "canh_bao": (
                "Hiện KHÔNG có chính sách hỗ trợ lãi suất nào của chủ đầu tư còn hiệu lực. "
                "Lãi suất vay phụ thuộc ngân hàng, chưa có cơ sở để tính trả góp."
            ),
        }
        if da_het is not None:
            thong_tin["chinh_sach_gan_nhat_da_het_han"] = {
                "ten": da_het.ten,
                "tran_lai_suat_phan_tram": da_het.tran_lai_suat,
                "het_hieu_luc_ngay": da_het.hieu_luc_den.isoformat(),
                "nguon": da_het.nguon,
            }
        return thong_tin

    def _theo_chinh_sach(
        self,
        chinh_sach: ChinhSachVay,
        args: KhoanVayArgs,
        can_vay: float,
        ty_le_vay: float,
        gia: float,
    ) -> dict[str, Any]:
        ky_han = args.ky_han_vay_nam or chinh_sach.ky_han_vay_nam_min
        muc_vay = chinh_sach.muc_vay_phu_hop(ty_le_vay)

        thong_tin: dict[str, Any] = {
            "chinh_sach_ho_tro_lai_suat": {
                "ten": chinh_sach.ten,
                "tran_lai_suat_phan_tram": chinh_sach.tran_lai_suat,
                "so_thang_khoa_tran": chinh_sach.so_thang_khoa,
                "hieu_luc_den": chinh_sach.hieu_luc_den.isoformat(),
                "nguon": chinh_sach.nguon,
            },
        }

        # Vượt mức hỗ trợ thì KHÔNG tính trả góp. Tính theo trần 6% ở đây là
        # ngụ ý khách được hưởng mức đó, trong khi chính sách vừa nói là không —
        # cùng loại sai với việc bịa hẳn một con số, chỉ kín đáo hơn.
        if muc_vay is None:
            thong_tin["canh_bao"] = (
                f"Tỷ lệ vay {ty_le_vay:.1f}% vượt mức hỗ trợ cao nhất "
                f"({max(chinh_sach.muc_vay_ho_tro)}%) của chính sách, nên chưa tính được trả góp "
                "theo trần lãi suất. Cần tăng vốn tự có hoặc chọn căn giá thấp hơn."
            )
            return thong_tin

        tra_thang = _tra_hang_thang(can_vay, chinh_sach.tran_lai_suat, ky_han * 12)
        thong_tin.update(
            {
                "ky_han_vay_nam": ky_han,
                # Nêu cả hai đơn vị: người đọc nghĩ bằng "triệu/tháng", còn phần
                # còn lại của kết quả tính bằng tỷ. Để model tự đổi là mời nó
                # nhầm dấu phẩy ba chữ số.
                "tra_hang_thang_trieu": round(tra_thang * 1_000, 1),
                "tra_hang_thang_ty": round(tra_thang, 4),
                "muc_vay_ap_dung_phan_tram": muc_vay,
                "cac_goi_ho_tro": _cac_goi(chinh_sach, muc_vay, gia),
                "sau_khi_het_khoa_tran": (
                    f"Sau {chinh_sach.so_thang_khoa} tháng, lãi suất thả nổi theo ngân hàng — "
                    "chưa xác định được, cần hỏi ngân hàng tại thời điểm đó."
                ),
            }
        )
        if chinh_sach.tran_sau_uu_dai is not None:
            thong_tin["tiep_suc_sau_uu_dai"] = (
                f"Gói tối đa {chinh_sach.goi_duoc_tiep_suc_toi_da_thang} tháng còn được hỗ trợ "
                f"thêm {chinh_sach.so_thang_tiep_suc} tháng với trần {chinh_sach.tran_sau_uu_dai}%/năm."
            )
        return thong_tin
