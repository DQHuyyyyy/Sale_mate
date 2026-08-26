"""Dựng báo cáo điểm — bám khuôn 'Mẫu báo cáo tổng hợp' ở sheet 5 của plan."""

from __future__ import annotations

from typing import Any

from eval.runner.phan_loai_loi import gom_theo_tang

# Thang hành động của plan (sheet '5. Ngưỡng & Báo cáo').
MUC = [(0.8, "Tốt", "Theo dõi, duy trì"), (0.6, "Cần cải thiện", "Phân tích lỗi, lên kế hoạch")]


def _nhan_muc(ty_le: float) -> str:
    for nguong, ten, hanh_dong in MUC:
        if ty_le >= nguong:
            return f"{ten} — {hanh_dong}"
    return "Vấn đề nghiêm trọng — điều tra ngay, không đưa vào demo"


def _ky_hieu(dat: bool | None) -> str:
    return {True: "✅ đạt", False: "❌ không đạt"}.get(dat, "⏸ chưa kết luận")


def _trung_binh(so: list[float]) -> str:
    """Luôn kèm cỡ mẫu. 'Faithfulness 1.00' đọc rất mạnh cho tới lúc biết nó là
    trung bình của đúng hai câu — con số không có mẫu đi kèm là con số dễ bị
    trích ra khỏi ngữ cảnh và mang lên slide."""
    return f"{sum(so) / len(so):.2f} (n={len(so)})" if so else "— (n=0)"


def _phan_nhom(dong: list[dict[str, Any]]) -> list[str]:
    gom: dict[str, list[dict[str, Any]]] = {}
    for d in dong:
        gom.setdefault(d.get("nhom", "?"), []).append(d)

    ra = ["## Theo nhóm", "", "| Nhóm | Đạt | Không đạt | Chưa kết luận | Tỷ lệ đạt |", "|---|---|---|---|---|"]
    for nhom, ds in gom.items():
        dat = sum(1 for d in ds if d["dat"] is True)
        fail = sum(1 for d in ds if d["dat"] is False)
        cho = sum(1 for d in ds if d["dat"] is None)
        da_ket_luan = dat + fail
        ty_le = f"{dat / da_ket_luan * 100:.0f}%" if da_ket_luan else "—"
        ra.append(f"| {nhom} | {dat} | {fail} | {cho} | {ty_le} |")
    return [*ra, ""]


def _phan_chi_tiet(dong: list[dict[str, Any]]) -> list[str]:
    ra = [
        "## Từng câu",
        "",
        "| ID | Kết luận | Judge | Faith. | Relev. | Tầng lỗi | Ghi chú |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in dong:
        ghi = "; ".join(d["vi_pham"]) or d["ly_do_judge"] or d["loi_judge"] or ""
        if d["can_nguoi"]:
            ghi = f"**cần người** — {ghi}" if ghi else "**cần người**"
        if d["can_db"]:
            ghi = f"**cần đối chiếu DB** — {ghi}" if ghi else "**cần đối chiếu DB**"
        ra.append(
            f"| {d['ma']} | {_ky_hieu(d['dat'])} | {d['diem_judge'] or '—'}/5 "
            f"| {d['faithfulness'] if d['faithfulness'] is not None else '—'} "
            f"| {d['answer_relevancy'] if d['answer_relevancy'] is not None else '—'} "
            f"| {d['tang_loi'] or '—'} | {ghi[:150]} |"
        )
    return [*ra, ""]


def _phan_tang_loi(dong: list[dict[str, Any]]) -> list[str]:
    gom = gom_theo_tang(dong)
    if not gom:
        return ["## Phân loại lỗi theo tầng", "", "Không case nào bị xếp lỗi.", ""]
    ra = ["## Phân loại lỗi theo tầng", "", "| Tầng | Case | Giải thích |", "|---|---|---|"]
    for tang, mas in sorted(gom.items(), key=lambda kv: -len(kv[1])):
        vi_du = next(d["giai_thich_loi"] for d in dong if d.get("tang_loi") == tang)
        ra.append(f"| `{tang}` | {', '.join(mas)} | {vi_du} |")
    return [*ra, ""]


def _phan_cho_nguoi(dong: list[dict[str, Any]], bo_qua: list[dict[str, Any]]) -> list[str]:
    can = [d for d in dong if d["can_nguoi"] or d["can_db"] or (d["diem_judge"] or 5) <= 2]
    ra = ["## Việc còn lại cho người", "", "Bộ chấm KHÔNG tự kết luận những case này.", ""]
    if can:
        ra += ["| ID | Vì sao | Cần làm gì |", "|---|---|---|"]
        for d in can:
            vi_sao = "Judge chấm ≤2" if (d["diem_judge"] or 5) <= 2 else "plan yêu cầu"
            ra.append(f"| {d['ma']} | {vi_sao} | {(d['can_nguoi'] or d['can_db'])[:160]} |")
        ra.append("")
    for b in bo_qua:
        ra.append(f"- **{b['ma']}** chưa chạy: {b['ly_do']}")
    return [*ra, ""]


def _phan_xung_dot(dong: list[dict[str, Any]]) -> list[str]:
    xung = [d for d in dong if d["ghi_chu_xung_dot"]]
    if not xung:
        return []
    ra = ["## Xung đột giữa dataset và hệ thống", ""]
    for d in xung:
        ra += [f"**{d['ma']}** — {_ky_hieu(d['dat'])}", "", d["ghi_chu_xung_dot"], ""]
    return ra


def dung_bang_diem(goi: dict[str, Any]) -> str:
    dong = goi["dong"]
    dat = sum(1 for d in dong if d["dat"] is True)
    fail = sum(1 for d in dong if d["dat"] is False)
    ch = goi.get("cau_hinh_lan_chay", {})

    ra = [
        "# Bảng điểm — golden dataset SalesMate",
        "",
        f"- Nguồn: `{goi['nguon']}`  ·  Judge: `{goi['model_judge']}`",
        f"- Hệ thống lúc chạy: model trả lời `{ch.get('llm_model_answer')}`, "
        f"leo thang `{ch.get('che_do_leo_thang')}`, ngưỡng độ phủ {ch.get('coverage_threshold')}",
        f"- Kết luận được: **{dat} đạt / {fail} không đạt** trên {len(dong)} câu đã chấm"
        + (f"  ·  mức: {_nhan_muc(dat / (dat + fail))}" if dat + fail else ""),
        f"- Faithfulness TB: {_trung_binh([d['faithfulness'] for d in dong if d['faithfulness'] is not None])}"
        f"  ·  Answer Relevancy TB: "
        f"{_trung_binh([d['answer_relevancy'] for d in dong if d['answer_relevancy'] is not None])}",
        "",
        "> Context Recall **chưa đo được**: cần đáp án chuẩn do expert viết (plan Ngày 1),"
        " hiện chưa có câu RAG nào có.",
        "",
        "## Chống bias của Judge",
        "",
        *[f"- {d}" for d in goi.get("canh_bao_bias", [])],
        "",
    ]
    ra += _phan_nhom(dong)
    ra += _phan_tang_loi(dong)
    ra += _phan_xung_dot(dong)
    ra += _phan_chi_tiet(dong)
    ra += _phan_cho_nguoi(dong, goi.get("bo_qua", []))
    return "\n".join(ra) + "\n"
