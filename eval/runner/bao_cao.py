"""Báo cáo tổng hợp một lần chạy — đúng khuôn "Mẫu báo cáo" ở sheet 5 của plan.

    python -m eval.runner.bao_cao eval/results/diem_<...>.json [diem_<truoc>.json]

Khác `bang_diem.py` ở mục đích: file kia là bảng làm việc để soi từng câu, file
này là thứ mang đi báo cáo — số liệu theo nhóm, độ trễ, chi phí, so với lần chạy
trước, và danh sách việc còn lại.

Sheet 5 yêu cầu đúng sáu mục, module này bám sát:
  1. Ngày chạy · phiên bản hệ thống
  2. Tổng số câu / pass / fail theo từng nhóm
  3. Faithfulness, Answer Relevancy trung bình
  4. Case fail kèm nguyên nhân đã phân loại theo tầng
  5. So với lần chạy trước — có regression không
  6. Việc cần làm tiếp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.runner import chi_so  # noqa: E402
from eval.runner.bang import _phan_vi  # noqa: E402

# Ngưỡng độ trễ đã chốt 26/08/2026 — đo thứ khách CHỜ, không đo tổng một lượt.
NGUONG_CHU_DAU, NGUONG_DOC_XONG = 8.0, 15.0


def _dem(dong: list[dict[str, Any]], gia_tri: bool | None) -> int:
    return sum(1 for d in dong if d["dat"] is gia_tri)


def _ty_le(dong: list[dict[str, Any]]) -> str:
    dat, fail = _dem(dong, True), _dem(dong, False)
    return f"{dat / (dat + fail) * 100:.0f}%" if dat + fail else "—"


def _muc_do(dong: list[dict[str, Any]]) -> str:
    """Thang hành động của plan (sheet 5), tính trên số câu ĐÃ kết luận."""
    dat, fail = _dem(dong, True), _dem(dong, False)
    if not dat + fail:
        return "chưa đủ dữ liệu"
    ty = dat / (dat + fail)
    if ty >= 0.8:
        return f"**Tốt** ({ty:.0%}) — theo dõi, duy trì"
    if ty >= 0.6:
        return f"**Cần cải thiện** ({ty:.0%}) — phân tích lỗi, lên kế hoạch"
    return f"**Vấn đề nghiêm trọng** ({ty:.0%}) — không đưa vào demo cho tới khi cải thiện"


def _phan_mo_dau(diem: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    ch = diem.get("cau_hinh_lan_chay", {})
    dong = diem["dong"]
    return [
        "# Báo cáo eval SalesMate",
        "",
        f"- **Ngày chạy:** {raw.get('chay_luc', '?')}  ·  **commit** `{raw.get('commit', '?')}`"
        + (f"  ·  nhãn `{raw['nhan']}`" if raw.get("nhan") else ""),
        f"- **Hệ thống:** model trả lời `{ch.get('llm_model_answer')}`, "
        f"leo thang `{ch.get('che_do_leo_thang')}` bằng `{ch.get('orchestrator_model')}`, "
        f"ngưỡng độ phủ {ch.get('coverage_threshold')}",
        f"- **Chấm bằng:** rule-based + đối chiếu database + LLM Judge `{diem.get('model_judge')}`",
        "",
        "## 1. Kết quả tổng",
        "",
        "| Đạt | Không đạt | Chưa kết luận | Tổng chấm |",
        "|---|---|---|---|",
        f"| **{_dem(dong, True)}** | **{_dem(dong, False)}** | {_dem(dong, None)} | {len(dong)} |",
        "",
        f"Mức: {_muc_do(dong)}",
        "",
    ]


def _phan_theo_nhom(dong: list[dict[str, Any]]) -> list[str]:
    gom: dict[str, list[dict[str, Any]]] = {}
    for d in dong:
        gom.setdefault(d.get("nhom", "?"), []).append(d)

    ra = [
        "## 2. Theo nhóm chỉ số",
        "",
        "| Nhóm | Đạt | Không đạt | Chưa kết luận | Tỷ lệ đạt |",
        "|---|---|---|---|---|",
    ]
    for nhom, ds in gom.items():
        ra.append(f"| {nhom} | {_dem(ds, True)} | {_dem(ds, False)} | {_dem(ds, None)} | {_ty_le(ds)} |")
    return [*ra, ""]


def _phan_chi_so(dong: list[dict[str, Any]], raw: dict[str, Any]) -> list[str]:
    faith = [d["faithfulness"] for d in dong if d["faithfulness"] is not None]
    relev = [d["answer_relevancy"] for d in dong if d["answer_relevancy"] is not None]
    chay = [d for d in raw.get("ket_qua", []) if d.get("da_chay", True) and not d.get("loi")]
    dau = [float(d["giay_toi_chu_dau"]) for d in chay if d.get("giay_toi_chu_dau") is not None]
    xong = [float(d["giay_het_token"]) for d in chay if d.get("giay_het_token") is not None]

    def tb(so: list[float]) -> str:
        return f"{sum(so) / len(so):.2f} (n={len(so)})" if so else "— (n=0)"

    def do_tre(ten: str, so: list[float], nguong: float) -> str:
        if not so:
            return f"| {ten} | — | — | — |"
        p95 = _phan_vi(so, 0.95)
        return f"| {ten} | {_phan_vi(so, 0.5):.1f}s | {p95:.1f}s | ≤ {nguong:.0f}s {'✅' if p95 <= nguong else '⚠️'} |"

    return [
        "## 4. Chỉ số chất lượng và độ trễ",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Faithfulness TB | {tb(faith)} |",
        f"| Answer Relevancy TB | {tb(relev)} |",
        "| Context Recall | xem mục 3 — đã có đáp án chuẩn ở `dap_an_chuan.json` |",
        "",
        "**Độ trễ** — đo thứ khách CHỜ, không đo tổng một lượt (phần sinh gợi ý chạy",
        "sau khi chữ đã hết nên khách đang đọc chứ không ngồi đợi):",
        "",
        "| | P50 | P95 | Ngưỡng |",
        "|---|---|---|---|",
        do_tre("Tới chữ đầu tiên", dau, NGUONG_CHU_DAU),
        do_tre("Đọc xong câu trả lời", xong, NGUONG_DOC_XONG),
        "",
    ]


def _phan_ma_tran(raw: dict[str, Any]) -> list[str]:
    """Ma trận chỉ số sheet 3 — tính lại từ kết quả thô, không tốn credit."""
    try:
        return ["## 3. Ma trận chỉ số (sheet 3)", "", *chi_so.dung_bang(chi_so.tinh_tat_ca(raw)).splitlines()[2:], ""]
    except Exception as exc:  # noqa: BLE001 - thiếu Qdrant thì bỏ mục, không dừng báo cáo
        return ["## 3. Ma trận chỉ số (sheet 3)", "", f"Chưa tính được: {exc}", ""]


def _phan_that_bai(dong: list[dict[str, Any]]) -> list[str]:
    fail = [d for d in dong if d["dat"] is False]
    if not fail:
        return ["## 5. Case không đạt", "", "Không có case nào không đạt.", ""]

    ra = ["## 5. Case không đạt — kèm tầng lỗi", "", "| ID | Nhóm | Tầng | Vì sao |", "|---|---|---|---|"]
    for d in fail:
        vi_sao = "; ".join(d["vi_pham"]) or d["ly_do_judge"] or "—"
        if d.get("ghi_chu_xung_dot"):
            vi_sao = "**xung đột dataset, không phải lỗi hệ thống** — " + vi_sao
        ra.append(f"| {d['ma']} | {d['nhom']} | `{d['tang_loi'] or '—'}` | {vi_sao[:170]} |")
    return [*ra, ""]


def _phan_so_sanh(dong: list[dict[str, Any]], truoc: dict[str, Any] | None) -> list[str]:
    if truoc is None:
        return ["## 6. So với lần chạy trước", "", "Không có lần chạy trước để so.", ""]

    cu = {d["ma"]: d for d in truoc["dong"]}
    doi = [(d["ma"], cu[d["ma"]]["dat"], d["dat"]) for d in dong if d["ma"] in cu and cu[d["ma"]]["dat"] != d["dat"]]
    hoi_quy = [x for x in doi if x[1] is True and x[2] is not True]

    ra = [
        "## 6. So với lần chạy trước",
        "",
        f"Nguồn: `{truoc.get('nguon', '?')}`",
        "",
        f"- Đạt: {_dem(list(cu.values()), True)} → **{_dem(dong, True)}**",
        f"- Không đạt: {_dem(list(cu.values()), False)} → **{_dem(dong, False)}**",
        "",
    ]
    if hoi_quy:
        ra += ["⚠️ **CÓ HỒI QUY** — case từng đạt nay không đạt:", ""]
        ra += [f"- `{ma}`: {cu_dat} → {moi}" for ma, cu_dat, moi in hoi_quy]
    else:
        ra.append("✅ **Không có hồi quy** — không case nào từ đạt chuyển sang không đạt.")
    if doi and not hoi_quy:
        ra += ["", "Thay đổi theo hướng tốt lên:"] + [f"- `{ma}`: {c} → {m}" for ma, c, m in doi]
    return [*ra, ""]


def _phan_viec_tiep(dong: list[dict[str, Any]], bo_qua: list[dict[str, Any]]) -> list[str]:
    ra = ["## 8. Việc cần làm tiếp", ""]
    for d in [x for x in dong if x["dat"] is False and not x.get("ghi_chu_xung_dot")]:
        ra.append(f"- **{d['ma']}** — sửa ở tầng `{d['tang_loi'] or 'chưa xếp'}`: {d['giai_thich_loi'][:140]}")
    for d in [x for x in dong if x.get("ghi_chu_xung_dot")]:
        ra.append(f"- **{d['ma']}** — chốt lại tiêu chí chấm trong golden dataset, không sửa hệ thống")
    for d in [x for x in dong if x["dat"] is None]:
        ra.append(
            f"- **{d['ma']}** — chưa kết luận được: {(d['can_nguoi'] or d['can_db'] or 'không có luật chấm')[:120]}"
        )
    for b in bo_qua:
        ra.append(f"- **{b['ma']}** — chưa chạy: {b['ly_do'][:120]}")
    return [*ra, ""]


def _phan_can_nguoi(dong: list[dict[str, Any]]) -> list[str]:
    """Gói việc cho NGƯỜI duyệt — Ngày 5 của plan và mục cuối sheet 4.

    Plan cấm để LLM Judge tự quyết pass/fail ở ba nhóm: case pháp lý (R03), case
    HITL (H01, H02), và bất kỳ câu nào Judge chấm 1-2 điểm (nghi bịa). Bộ chấm
    tự động không được kết luận thay — nó chỉ gom sẵn thứ người cần đọc.
    """
    can = [d for d in dong if d["can_nguoi"] or (d["diem_judge"] or 5) <= 2]
    if not can:
        return []
    ra = [
        "## 7. Cần người duyệt — bộ chấm KHÔNG tự kết luận",
        "",
        "| ID | Vì sao bắt buộc | Máy đang chấm | Người duyệt |",
        "|---|---|---|---|",
    ]
    for d in can:
        vi_sao = "Judge chấm ≤2" if (d["diem_judge"] or 5) <= 2 else "plan yêu cầu"
        may = {True: "đạt", False: "không đạt"}.get(d["dat"], "chưa kết luận")
        ra.append(f"| {d['ma']} | {vi_sao} | {may} | ☐ đạt  ☐ không đạt |")
    return [*ra, ""]


def dung_bao_cao(diem: dict[str, Any], raw: dict[str, Any], truoc: dict[str, Any] | None) -> str:
    dong = diem["dong"]
    phan = _phan_mo_dau(diem, raw)
    phan += _phan_theo_nhom(dong)
    phan += _phan_ma_tran(raw)
    phan += _phan_chi_so(dong, raw)
    phan += _phan_that_bai(dong)
    phan += _phan_so_sanh(dong, truoc)
    phan += _phan_can_nguoi(dong)
    phan += _phan_viec_tiep(dong, diem.get("bo_qua", []))
    phan += ["## Ghi chú về độ tin của bài đo", "", *[f"- {x}" for x in diem.get("canh_bao_bias", [])], ""]
    return "\n".join(phan) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dựng báo cáo tổng hợp từ file điểm")
    parser.add_argument("diem", help="File diem_*.json")
    parser.add_argument("truoc", nargs="?", help="File diem_*.json của lần chạy trước, để so")
    args = parser.parse_args()

    duong = Path(args.diem)
    diem = json.loads(duong.read_text(encoding="utf-8"))
    raw = json.loads((duong.parent / diem["nguon"]).read_text(encoding="utf-8"))
    truoc = json.loads(Path(args.truoc).read_text(encoding="utf-8")) if args.truoc else None

    ra = duong.with_name(duong.stem.replace("diem_", "baocao_") + ".md")
    ra.write_text(dung_bao_cao(diem, raw, truoc), encoding="utf-8")
    print(f"Đã ghi: {ra}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
