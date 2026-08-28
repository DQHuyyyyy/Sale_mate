"""Ma trận chỉ số của plan (sheet 3) — phần chưa có trong bảng điểm.

    python -m eval.runner.chi_so eval/results/raw_<...>.json

Bốn chỉ số ở đây tính TỪ DỮ LIỆU ĐÃ GHI, không gọi model, không tốn credit:

  - Tool selection accuracy   (T01-T06, H01)  ngưỡng 100%
  - Parameter accuracy        (T01-T05)       ngưỡng 100%
  - Tool success/recovery     (T06)           ngưỡng 100%
  - Không lặp hành động       (M02a-b)        ngưỡng 100%

Context Recall thì KHÁC: nó cần đoạn văn bản truy hồi được, mà runner không ghi
lại. Nên `context_recall()` tự chạy `Retriever` một lần nữa cho câu hỏi đó —
đường độc lập, cùng nguyên tắc với `doi_chieu_db`. Tốn một lượt embedding
(~$0.000002), không gọi model sinh chữ.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DUONG_DAP_AN = Path(__file__).resolve().parent / "dap_an_chuan.json"

# Tool ĐÚNG cho từng case, suy từ cột "Kỳ vọng đúng" của golden dataset.
# Ba tool tồn kho nhường nhau theo SỐ mã căn trong câu: 0 -> search/summary,
# 1 -> lookup, >=2 -> so_sanh_can. Xem CLAUDE.md mục "Thêm một tool".
TOOL_MONG_DOI: dict[str, set[str]] = {
    "T01": {"inventory_search"},
    "T02": {"inventory_lookup"},
    "T03": {"inventory_search"},
    "T04": {"so_sanh_can"},
    "T05": {"inventory_search"},
    "T06": {"inventory_lookup"},
    "H01": {"dat_coc"},
}

# Tham số tool PHẢI có, suy từ chính câu hỏi. Chỉ khai thứ câu hỏi nêu tường
# minh — thêm điều kiện không có trong câu là tự dựng một bài thi khác.
THAM_SO_MONG_DOI: dict[str, dict[str, Any]] = {
    "T01": {"unit_type": "Studio", "subdivision": "Ocean Park 3", "price_max": 2.3},
    "T02": {"unit_code": "VOP518"},
    "T03": {"unit_type": "2PN", "subdivision": "Ocean Park 1"},
    "T04": {"unit_codes": ["VOP518", "VOP703"]},
    "T05": {"subdivision": "Ocean Park 1", "unit_type": "2PN"},
}


@dataclass
class KetQuaChiSo:
    ten: str
    dat: int
    tong: int
    nguong: str
    chi_tiet: list[str]

    @property
    def ty_le(self) -> float:
        return self.dat / self.tong if self.tong else 0.0


def _tools_cua(d: dict[str, Any]) -> set[str]:
    """Tool do NODE `tools` chạy — KHÔNG tính tool orchestrator thêm vào.

    Chỉ số này đo đường tất định: `intents` + `build_args` có chọn đúng tool cho
    câu hỏi không. Gộp cả tool orchestrator thêm vào là che mất đúng thứ cần đo —
    một `build_args` hụt sẽ được cứu và bảng điểm báo 100%.
    """
    for b in d.get("buoc", []):
        if b.get("step") == "tools":
            return set(b.get("tools") or [])
    return set()


def _filters_cua(d: dict[str, Any]) -> dict[str, Any]:
    for b in d.get("buoc", []):
        if b.get("step") == "tools":
            return b.get("filters") or {}
    return {}


def tool_selection(rows: dict[str, dict[str, Any]]) -> KetQuaChiSo:
    dat, chi_tiet = 0, []
    co = {m: v for m, v in TOOL_MONG_DOI.items() if m in rows}
    for ma, mong in co.items():
        thuc = _tools_cua(rows[ma])
        if mong & thuc:
            dat += 1
        else:
            chi_tiet.append(f"{ma}: mong {sorted(mong)}, thực tế {sorted(thuc) or 'không tool nào'}")
    return KetQuaChiSo("Tool selection accuracy", dat, len(co), "100%", chi_tiet)


def parameter_accuracy(rows: dict[str, dict[str, Any]]) -> KetQuaChiSo:
    """Tham số truyền vào tool có đúng ĐỊNH DẠNG dữ liệu thật không.

    Plan ghi đây là nguyên nhân gốc của bug B01 và phải theo dõi để không tái
    diễn: chat lọc `2PN` trong khi DB lưu `2PN, 1WC` thì hai bên ra hai con số.
    """
    dat, chi_tiet = 0, []
    co = {m: v for m, v in THAM_SO_MONG_DOI.items() if m in rows}
    for ma, mong in co.items():
        thuc = _filters_cua(rows[ma])
        phang = {k: v for tham in thuc.values() if isinstance(tham, dict) for k, v in tham.items()}
        thieu = [k for k, v in mong.items() if not _khop(phang.get(k), v)]
        if not thieu:
            dat += 1
        else:
            chi_tiet.append(f"{ma}: thiếu/sai {thieu} — thực tế {phang or 'không có tham số'}")
    return KetQuaChiSo("Parameter accuracy", dat, len(co), "100%", chi_tiet)


def _khop(thuc: Any, mong: Any) -> bool:
    """So khớp mềm: chuỗi thì chấp nhận tiền tố (DB lưu '2PN, 1WC' cho '2PN')."""
    if thuc is None:
        return False
    if isinstance(mong, list):
        return isinstance(thuc, list) and {str(x).upper() for x in mong} <= {str(x).upper() for x in thuc}
    if isinstance(mong, str):
        return str(thuc).upper().startswith(mong.upper())
    return abs(float(thuc) - float(mong)) < 1e-6


def tool_recovery(rows: dict[str, dict[str, Any]]) -> KetQuaChiSo:
    """Tool trả rỗng thì agent phải báo không tìm thấy, KHÔNG bịa số liệu."""
    import re

    chi_tiet = []
    co = [m for m in ("T06",) if m in rows]
    dat = 0
    for ma in co:
        cau = rows[ma].get("cau_tra_loi", "")
        bia = re.search(r"\d+[.,]?\d*\s*(tỷ|tỉ|m2|m²)", cau, re.IGNORECASE)
        if bia is None:
            dat += 1
        else:
            chi_tiet.append(f"{ma}: nêu số liệu {bia.group(0)!r} cho mã không tồn tại")
    return KetQuaChiSo("Tool success / recovery rate", dat, len(co), "100%", chi_tiet)


def khong_lap_hanh_dong(rows: dict[str, dict[str, Any]]) -> KetQuaChiSo:
    """Lượt 2 của M02 chỉ hỏi thông tin — không được chạy lại `dat_coc`."""
    chi_tiet = []
    co = [m for m in ("M02b",) if m in rows]
    dat = 0
    for ma in co:
        if "dat_coc" in _tools_cua(rows[ma]):
            chi_tiet.append(f"{ma}: `dat_coc` chạy lại dù lượt này chỉ hỏi hướng căn")
        else:
            dat += 1
    return KetQuaChiSo("KHÔNG lặp hành động ngoài ý muốn", dat, len(co), "100%", chi_tiet)


def context_recall(rows: dict[str, dict[str, Any]]) -> KetQuaChiSo:
    """Bao nhiêu khẳng định của đáp án chuẩn có mặt trong ngữ cảnh truy hồi được.

    Tự chạy `Retriever` lần nữa thay vì đọc lại `chunks` của runner: runner chỉ
    ghi SỐ đoạn và độ phủ, không ghi text. Chạy lại là đường độc lập, cùng
    nguyên tắc với `doi_chieu_db` — và nó đo đúng thứ Context Recall hỏi: thông
    tin cần có, truy hồi có lấy về được không.

    Câu `phai_tu_choi` không có khẳng định nào nên KHÔNG tính vào chỉ số này.
    """
    dap_an = {k: v for k, v in json.loads(DUONG_DAP_AN.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    co = {m: v for m, v in dap_an.items() if m in rows and not v["phai_tu_choi"]}
    if not co:
        return KetQuaChiSo("Context Recall", 0, 0, "≥ 0.8", ["Không câu nào có đáp án chuẩn cần truy hồi"])

    try:
        chunks_cua = _truy_hoi_lai({m: v["cau_hoi"] for m, v in co.items()})
    except Exception as exc:  # noqa: BLE001 - thiếu Qdrant thì bỏ chỉ số, không dừng cả bộ
        return KetQuaChiSo("Context Recall", 0, 0, "≥ 0.8", [f"Không truy hồi được: {exc}"])

    theo_ma = _recall_theo_ma(co, chunks_cua)
    tong_kd = sum(t for _, t, _ in theo_ma.values())
    dat_kd = sum(d for d, _, _ in theo_ma.values())
    chi_tiet = [f"{ma}: truy hồi KHÔNG chứa {thieu}" for ma, (_, _, thieu) in theo_ma.items() if thieu]
    return KetQuaChiSo("Context Recall", dat_kd, tong_kd, "≥ 0.8", chi_tiet)


def _recall_theo_ma(co: dict[str, Any], chunks_cua: dict[str, str]) -> dict[str, tuple[int, int, list[str]]]:
    ra: dict[str, tuple[int, int, list[str]]] = {}
    for ma, v in co.items():
        van_ban = chunks_cua.get(ma, "").lower()
        thieu = [k for k in v["khang_dinh"] if k.lower() not in van_ban]
        ra[ma] = (len(v["khang_dinh"]) - len(thieu), len(v["khang_dinh"]), thieu)
    return ra


def recall_theo_ma(rows: dict[str, dict[str, Any]]) -> dict[str, tuple[int, int, list[str]]]:
    """Context Recall tách theo từng case — để xếp TẦNG LỖI cho đúng.

    Độ phủ cao KHÔNG có nghĩa là truy hồi lấy đúng tài liệu. Ca thật, R01: cả 5
    đoạn đều từ "Chính sách hỗ trợ lãi suất chung" với độ phủ 0,642, trong khi
    hai tài liệu Ưu đãi OP2/OP3 chứa đúng câu "THANH TOÁN SỚM · ƯU ĐÃI 9%" thì
    không được lấy lần nào. Model từ chối là ĐÚNG với thứ nó được đưa.

    Xếp ca đó vào tầng `generate` (như phép kiểm theo độ phủ vẫn làm) là cử
    người đi sửa prompt, trong khi chỗ hỏng là truy hồi.
    """
    dap_an = {k: v for k, v in json.loads(DUONG_DAP_AN.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    co = {m: v for m, v in dap_an.items() if m in rows and not v["phai_tu_choi"]}
    if not co:
        return {}
    try:
        return _recall_theo_ma(co, _truy_hoi_lai({m: v["cau_hoi"] for m, v in co.items()}))
    except Exception:  # noqa: BLE001 - thiếu Qdrant thì không xếp lại tầng, giữ nguyên
        return {}


def doan_truy_hoi(cau_hoi: str) -> list[str]:
    """Các đoạn `Retriever` lấy về cho một câu — đầu vào của Context Precision.

    Trả list từng đoạn RỜI (không ghép) vì precision đếm theo đoạn: bao nhiêu
    trong top-k thật sự liên quan.
    """
    import asyncio

    return asyncio.run(doan_truy_hoi_async(cau_hoi))


async def doan_truy_hoi_async(cau_hoi: str) -> list[str]:
    """Bản async — gọi từ trong một coroutine đang chạy.

    `asyncio.run()` không lồng được, và `_cham_precision` vốn đã là coroutine.
    Tách hai bản thay vì để người gọi tự đoán: lồng nhầm thì lỗi hiện ra dưới
    dạng "coroutine was never awaited", rất khó lần ra.
    """
    from src.bootstrap import configure
    from src.core.container import container
    from src.rag.contracts import Retriever

    configure()
    retriever = container.resolve(Retriever)
    kq = await retriever.retrieve(cau_hoi)
    return [c.text for c in (getattr(kq, "chunks", kq) or [])]


def _truy_hoi_lai(cau_hoi: dict[str, str]) -> dict[str, str]:
    """Chạy Retriever thật cho từng câu, trả về text các đoạn lấy được."""
    import asyncio

    from src.bootstrap import configure
    from src.core.container import container
    from src.rag.contracts import Retriever

    configure()
    retriever = container.resolve(Retriever)

    async def chay() -> dict[str, str]:
        ra = {}
        for ma, q in cau_hoi.items():
            ket_qua = await retriever.retrieve(q)
            ra[ma] = "\n".join(c.text for c in getattr(ket_qua, "chunks", ket_qua) or [])
        return ra

    return asyncio.run(chay())


def tinh_tat_ca(raw: dict[str, Any]) -> list[KetQuaChiSo]:
    rows = {str(d["ma"]): d for d in raw.get("ket_qua", []) if d.get("da_chay", True) and not d.get("la_luot_xen")}
    return [
        tool_selection(rows),
        parameter_accuracy(rows),
        tool_recovery(rows),
        khong_lap_hanh_dong(rows),
        context_recall(rows),
    ]


def dung_bang(ket_qua: list[KetQuaChiSo]) -> str:
    dong = [
        "## Ma trận chỉ số — sheet 3 của plan",
        "",
        "| Chỉ số | Đạt | Tỷ lệ | Ngưỡng | |",
        "|---|---|---|---|---|",
    ]
    for k in ket_qua:
        if not k.tong:
            dong.append(f"| {k.ten} | — | — | {k.nguong} | chưa đo được |")
            continue
        nguong_so = 1.0 if k.nguong == "100%" else 0.8
        dong.append(
            f"| {k.ten} | {k.dat}/{k.tong} | {k.ty_le:.0%} | {k.nguong} | {'✅' if k.ty_le >= nguong_so else '⚠️'} |"
        )
    chi_tiet = [c for k in ket_qua for c in k.chi_tiet]
    if chi_tiet:
        dong += ["", "**Chi tiết chỗ chưa đạt:**", "", *[f"- {c}" for c in chi_tiet]]
    return "\n".join([*dong, ""])


def main() -> int:
    parser = argparse.ArgumentParser(description="Tính ma trận chỉ số sheet 3 từ file kết quả thô")
    parser.add_argument("file", help="Đường dẫn raw_*.json")
    args = parser.parse_args()

    duong = Path(args.file)
    ket_qua = tinh_tat_ca(json.loads(duong.read_text(encoding="utf-8")))
    bang = dung_bang(ket_qua)
    print(bang)

    ra = duong.with_name(duong.stem.replace("raw_", "chiso_") + ".md")
    ra.write_text(bang, encoding="utf-8")
    print(f"Đã ghi: {ra}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
