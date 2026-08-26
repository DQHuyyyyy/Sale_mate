"""Đọc bộ câu hỏi vàng từ `SalesMate_Golden_Dataset.xlsx`.

File .xlsx là NGUỒN SỰ THẬT DUY NHẤT của bộ 29 câu. Runner đọc thẳng từ đó chứ
không chép sang JSON: chép là dựng bản thứ hai nắm cùng một sự thật, rồi sửa
xlsx mà quên sửa JSON là eval đo một bộ câu hỏi không ai review.

Hai thứ .xlsx cố ý không diễn đạt được nằm ở `kich_ban.json`, khớp theo ID:

- A01 — ô câu hỏi chỉ ghi tóm tắt `[Trong 1 đoạn văn bản dài] ...`, không phải
  input chạy được. Đoạn văn thật nằm ở `input_day_du`.
- M03b — ô ghi `(Sau 3-4 lượt hỏi xen kẽ chủ đề khác)`; các lượt xen đó nằm ở
  `luot_xen` để mọi lần chạy đều xen đúng bấy nhiêu lượt, đo được so sánh được.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

THU_MUC = Path(__file__).resolve().parent
GOC_EVAL = THU_MUC.parent
DUONG_XLSX = GOC_EVAL / "SalesMate_Golden_Dataset.xlsx"
DUONG_KICH_BAN = THU_MUC / "kich_ban.json"
TEN_SHEET = "Golden Dataset"

# ID có dạng T01 / M01a / M03b — phần đầu là mã kịch bản, hậu tố a/b là thứ tự lượt.
_MA_KICH_BAN = re.compile(r"^([A-Z]+\d+)([a-z]?)$")


@dataclass
class CauHoi:
    """Một dòng của golden dataset, đã ghép thêm phần bổ sung nếu có."""

    ma: str
    nhom: str
    loai: str
    do_kho: str
    luot: int
    cau_hoi_xlsx: str
    ky_vong: str
    cach_cham: str
    ghi_chu: str
    input_chay: str = ""
    can_chuan_bi: str = ""
    luot_xen_truoc: list[str] = field(default_factory=list)
    kho_rieng: str = ""

    @property
    def chay_duoc(self) -> bool:
        """Case thiếu dữ liệu chuẩn bị thì không chạy — ghi rõ lý do thay vì fail giả."""
        return not self.can_chuan_bi and bool(self.input_chay)

    def ly_do_bo_qua(self, kho_dang_chay: str) -> str:
        """Lý do KHÔNG chạy case này, chuỗi rỗng nghĩa là chạy được.

        Case khai `kho_rieng` mà đang trỏ vào kho khác thì phải bỏ qua, không
        phải chạy đại. A02 hỏi về tài liệu chỉ có trong kho injection; chạy nó
        vào kho sản phẩm thì trợ lý từ chối vì không có tài liệu, dòng kết quả
        trông y hệt một ca chống injection thành công — trong khi chỉ dẫn giả
        chưa từng vào ngữ cảnh. Một case luôn "pass" mà không test gì là tệ hơn
        một case bị bỏ qua.
        """
        if self.can_chuan_bi:
            return self.can_chuan_bi
        if not self.input_chay:
            return "Không có input chạy được"
        if self.kho_rieng and self.kho_rieng != kho_dang_chay:
            return (
                f"Cần kho riêng '{self.kho_rieng}'. Chạy lại với --kho {self.kho_rieng} "
                f"và --base-url trỏ vào lõi AI đã bật với QDRANT_COLLECTION={self.kho_rieng}."
            )
        return ""


@dataclass
class KichBan:
    """Một hoặc nhiều lượt dùng chung hội thoại. Case đơn lượt cũng là kịch bản 1 lượt."""

    ma: str
    cac_luot: list[CauHoi]


def _doc_bo_sung() -> dict[str, dict[str, Any]]:
    if not DUONG_KICH_BAN.exists():
        return {}
    return json.loads(DUONG_KICH_BAN.read_text(encoding="utf-8"))


def _chu(o: Any) -> str:
    return "" if o is None else str(o).strip()


def _so_luot(o: Any) -> int:
    try:
        return int(str(o).strip())
    except (TypeError, ValueError):
        return 1


def doc_golden(duong_dan: Path = DUONG_XLSX) -> list[CauHoi]:
    """Đọc toàn bộ dòng dữ liệu của sheet 'Golden Dataset', giữ nguyên thứ tự file."""
    wb = openpyxl.load_workbook(duong_dan, data_only=True)
    ws = wb[TEN_SHEET]
    bo_sung = _doc_bo_sung()

    ket_qua: list[CauHoi] = []
    for hang in ws.iter_rows(min_row=2, values_only=True):
        ma = _chu(hang[0])
        if not ma:
            continue
        ket_qua.append(_dung_cau_hoi(ma, hang, bo_sung))
    return ket_qua


def _dung_cau_hoi(ma: str, hang: tuple[Any, ...], bo_sung: dict[str, dict[str, Any]]) -> CauHoi:
    """Ghép một dòng xlsx với phần bổ sung khớp ID (nếu có)."""
    cau_hoi_xlsx = _chu(hang[5])
    them = bo_sung.get(ma, {})
    return CauHoi(
        ma=ma,
        nhom=_chu(hang[1]),
        loai=_chu(hang[2]),
        do_kho=_chu(hang[3]),
        luot=_so_luot(hang[4]),
        cau_hoi_xlsx=cau_hoi_xlsx,
        ky_vong=_chu(hang[6]),
        cach_cham=_chu(hang[7]),
        ghi_chu=_chu(hang[8]) if len(hang) > 8 else "",
        input_chay=_chu(them.get("input_day_du")) or cau_hoi_xlsx,
        can_chuan_bi=_chu(them.get("can_chuan_bi")),
        luot_xen_truoc=list(them.get("luot_xen_truoc", [])),
        kho_rieng=_chu(them.get("chay_o_kho_rieng")),
    )


def gom_kich_ban(cau_hoi: list[CauHoi]) -> list[KichBan]:
    """Gom các lượt cùng mã kịch bản (M01a + M01b) vào một hội thoại."""
    theo_ma: dict[str, list[CauHoi]] = {}
    thu_tu: list[str] = []
    for c in cau_hoi:
        khop = _MA_KICH_BAN.match(c.ma)
        goc = khop.group(1) if khop else c.ma
        if goc not in theo_ma:
            theo_ma[goc] = []
            thu_tu.append(goc)
        theo_ma[goc].append(c)
    return [KichBan(ma=m, cac_luot=sorted(theo_ma[m], key=lambda c: (c.luot, c.ma))) for m in thu_tu]


def loc(kich_ban: list[KichBan], chi: list[str] | None, nhom: str | None) -> list[KichBan]:
    """Lọc theo mã (kịch bản hoặc lượt cụ thể) và theo nhóm chỉ số.

    Lọc ở mức KỊCH BẢN chứ không mức lượt: chạy riêng M01b mà bỏ M01a thì lượt 2
    không có gì để kế thừa, kết quả vô nghĩa.
    """
    ra = kich_ban
    if chi:
        can = {m.strip().upper() for m in chi if m.strip()}
        ra = [k for k in ra if k.ma.upper() in can or any(c.ma.upper() in can for c in k.cac_luot)]
    if nhom:
        n = nhom.strip().lower()
        ra = [k for k in ra if any(n in c.nhom.lower() for c in k.cac_luot)]
    return ra
