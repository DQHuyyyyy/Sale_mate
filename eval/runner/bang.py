"""Dựng bảng markdown từ file kết quả thô, để đọc bằng mắt trước khi chấm điểm.

Bảng này KHÔNG chấm pass/fail — ngày 2 chưa chấm. Nó chỉ bày ra đủ thứ cần để
nhìn một cái là biết lượt nào đáng ngờ: tool nào chạy, truy hồi được mấy đoạn,
độ phủ bao nhiêu, có leo thang không, còn mấy nguồn sau khi lọc.
"""

from __future__ import annotations

from typing import Any


def _rut(chu: str, dai: int) -> str:
    mot_dong = " ".join(str(chu).split())
    return mot_dong if len(mot_dong) <= dai else mot_dong[: dai - 1] + "…"


def _phan_vi(so: list[float], muc: float) -> float:
    """Phân vị kiểu 'nearest-rank' — 29 mẫu thì nội suy không nói thêm được gì."""
    if not so:
        return 0.0
    da_sap = sorted(so)
    vi_tri = max(0, min(len(da_sap) - 1, round(muc * len(da_sap) + 0.5) - 1))
    return da_sap[vi_tri]


def _dong_bang(d: dict[str, Any]) -> str:
    if not d.get("da_chay", True):
        return f"| {d['ma']} | {d['nhom']} | {_rut(d['cau_hoi_xlsx'], 40)} | — | — | — | — | — | BỎ QUA |"

    buoc = {b.get("step"): b for b in d.get("buoc", [])}
    tools = ",".join(
        dict.fromkeys(
            [t for b in d.get("buoc", []) for t in (b.get("tools") or []) if b.get("step") in {"tools", "orchestrate"}]
        )
    )
    tim = buoc.get("retrieve", {})
    truy_hoi = f"{tim.get('chunks', 0)}@{tim.get('coverage', 0)}" if tim else "—"
    leo = buoc.get("orchestrate", {}).get("luat", "") or "—"
    tinh_trang = "LỖI" if d.get("loi") else ("THIẾU DONE" if d.get("co_done") is False else "")
    if d.get("chinh_sach_chan"):
        tinh_trang = f"CHẶN ({d.get('chinh_sach_nhan')})"
    elif d.get("chinh_sach_nhan") not in (None, "", "binh_thuong"):
        tinh_trang = tinh_trang or f"cờ {d.get('chinh_sach_nhan')}"
    return (
        f"| {d['ma']} | {d['nhom']} | {_rut(d['cau_hoi_xlsx'] or d.get('cau_hoi', ''), 40)} "
        f"| {tools or '—'} | {truy_hoi} | {leo} | {len(d.get('nguon', []))} "
        f"| {d.get('giay_tong', 0):.1f}s | {tinh_trang or _rut(d.get('cau_tra_loi', ''), 60)} |"
    )


def _quan_sat_leo_thang(rows: list[dict[str, Any]], khai_bao: str) -> str:
    """Đếm số lượt THẬT SỰ leo thang, vì cấu hình khai báo có thể sai.

    `cau_hinh` đọc `.env` của máy chạy runner chứ không hỏi server, nên chạy vào
    một server bật bằng biến môi trường khác là phần đầu báo cáo ghi nhầm. Số
    lượt có bước `orchestrate` thì lấy từ chính luồng SSE, không nói dối được.
    """
    chay = [d for d in rows if d.get("da_chay", True) and not d.get("loi")]
    if not chay:
        return ""
    co = sum(1 for d in chay if any(b.get("step") == "orchestrate" for b in d.get("buoc", [])))
    canh_bao = ""
    if khai_bao == "moi_luot" and co == 0:
        canh_bao = "  ⚠️ khai `moi_luot` mà không lượt nào leo thang — server đang chạy cấu hình KHÁC"
    elif khai_bao == "tat" and co > 0:
        canh_bao = "  ⚠️ khai `tat` mà vẫn có lượt leo thang — server đang chạy cấu hình KHÁC"
    return f"- Quan sát: **{co}/{len(chay)}** lượt thật sự có bước `orchestrate`{canh_bao}"


def _phan_dau(goi: dict[str, Any]) -> list[str]:
    ch = goi.get("cau_hinh", {})
    return [
        "# Kết quả thô — golden dataset SalesMate",
        "",
        f"- Chạy lúc: {goi.get('chay_luc')}  ·  commit `{goi.get('commit')}`"
        + (f"  ·  nhãn `{goi['nhan']}`" if goi.get("nhan") else ""),
        f"- Gọi vào: `{goi.get('base_url')}/api/v1/chat/stream`",
        f"- Model trả lời: `{ch.get('llm_model_answer')}`  ·  model rẻ: `{ch.get('llm_model_fast')}`",
        f"- Leo thang: `{ch.get('che_do_leo_thang')}` với `{ch.get('orchestrator_model')}` "
        f"(bật: {ch.get('enable_orchestrator')}, effort `{ch.get('orchestrator_effort')}`)",
        f"- RAG: top_k={ch.get('retrieval_top_k')}, rerank_top_n={ch.get('rerank_top_n')}, "
        f"reranker=`{ch.get('reranker')}`, ngưỡng độ phủ={ch.get('coverage_threshold')}",
        f"- Vòng lặp agent: {ch.get('enable_agent_loop')}",
        _quan_sat_leo_thang(goi.get("ket_qua", []), str(ch.get("che_do_leo_thang", ""))),
        "",
        "⚠️ Dòng cấu hình đọc từ `.env` của máy chạy runner, không hỏi server. Dòng",
        "*Quan sát* mới lấy từ luồng SSE thật — tin dòng đó khi hai bên lệch nhau.",
        "",
    ]


# Ngưỡng đo THỨ KHÁCH CHỜ, không đo tổng một lượt. Đo thật cho thấy ~6,3s cuối
# mỗi lượt là bước sinh gợi ý, chạy SAU khi câu trả lời đã stream xong — khách
# đang đọc, không hề chờ nó. Tính cả 6,3s đó vào chỉ số là tự báo động giả.
NGUONG_CHU_DAU = 8.0
NGUONG_DOC_XONG = 15.0


def _cot_do_tre(ten: str, so: list[float], nguong: float | None = None) -> str:
    if not so:
        return f"| {ten} | — | — | — | — |"
    p95 = _phan_vi(so, 0.95)
    dat = "" if nguong is None else (" ✅" if p95 <= nguong else " ⚠️ vượt")
    muc = "—" if nguong is None else f"≤ {nguong:.0f}s{dat}"
    return f"| {ten} | {_phan_vi(so, 0.5):.2f}s | {p95:.2f}s | {max(so):.2f}s | {muc} |"


def _phan_do_tre(rows: list[dict[str, Any]]) -> list[str]:
    chay = [d for d in rows if d.get("da_chay", True) and not d.get("loi")]
    if not chay:
        return []
    dau = [float(d["giay_toi_chu_dau"]) for d in chay if d.get("giay_toi_chu_dau") is not None]
    xong = [float(d["giay_het_token"]) for d in chay if d.get("giay_het_token") is not None]
    tong = [float(d.get("giay_tong", 0)) for d in chay]

    return [
        "## Độ trễ",
        "",
        "| | P50 | P95 | Max | Ngưỡng |",
        "|---|---|---|---|---|",
        _cot_do_tre("Tới chữ đầu tiên", dau, NGUONG_CHU_DAU),
        _cot_do_tre("Đọc xong câu trả lời", xong, NGUONG_DOC_XONG),
        _cot_do_tre("Tổng, gồm cả sinh gợi ý", tong),
        "",
        "Hai dòng đầu là thứ khách thật sự chờ. Dòng ba chỉ để theo dõi, **không**",
        "có ngưỡng: phần chênh so với dòng hai là bước sinh gợi ý câu hỏi tiếp",
        "theo, chạy sau khi chữ đã hết nên khách đang đọc chứ không ngồi đợi.",
        "",
        f"Đo trên {len(chay)} lượt chạy được."
        + ("" if xong else "  ⚠️ Lần chạy này có trước khi runner đo `giay_het_token`."),
        "",
    ]


def _thoi_luong(d: dict[str, Any]) -> list[tuple[str, float]]:
    """Đổi các mốc kết thúc thành thời lượng từng bước."""
    moc: list[tuple[str, float]] = [
        (str(b.get("step", "?")), float(b.get("giay", 0.0))) for b in d.get("buoc", []) if "giay" in b
    ]
    if d.get("giay_toi_chu_dau") is not None:
        moc.append(("generate (tới chữ đầu)", float(d["giay_toi_chu_dau"])))
    if d.get("giay_het_token") is not None:
        moc.append(("stream chữ", float(d["giay_het_token"])))
    moc.append(("gợi ý + đóng luồng", float(d.get("giay_tong", 0.0))))

    ra: list[tuple[str, float]] = []
    truoc = 0.0
    for ten, den in moc:
        ra.append((ten, round(den - truoc, 2)))
        truoc = den
    return ra


def _phan_thoi_luong(rows: list[dict[str, Any]]) -> list[str]:
    """Trung bình thời lượng từng bước — để biết giây trôi đi đâu."""
    gom: dict[str, list[float]] = {}
    for d in rows:
        if not d.get("da_chay", True) or d.get("loi"):
            continue
        for ten, giay in _thoi_luong(d):
            gom.setdefault(ten, []).append(giay)
    if not gom:
        return []

    tong = sum(sum(v) / len(v) for v in gom.values())
    dong = [
        "## Giây trôi đi đâu",
        "",
        "Mốc lấy từ lúc event tới client, tức lúc node chạy xong. Node không phát",
        "event thì vô hình — thời gian của nó cộng vào bước hiện ngay sau.",
        "",
        "| Bước | Trung bình | Lớn nhất | % tổng | Số lượt |",
        "|---|---|---|---|---|",
    ]
    for ten, v in sorted(gom.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        tb = sum(v) / len(v)
        phan = (tb / tong * 100) if tong else 0
        dong.append(f"| {ten} | {tb:.2f}s | {max(v):.2f}s | {phan:.0f}% | {len(v)} |")
    return [*dong, ""]


def _phan_toan_van(rows: list[dict[str, Any]]) -> list[str]:
    ra = ["## Toàn văn từng lượt", ""]
    for d in rows:
        ra.append(f"### {d['ma']} — {d.get('nhom', '')} / {d.get('loai', '')}")
        ra.append("")
        ra.append(f"**Hỏi:** {d.get('cau_hoi') or d.get('cau_hoi_xlsx', '')}")
        ra.append("")
        if not d.get("da_chay", True):
            ra += [f"**BỎ QUA:** {d.get('ly_do_bo_qua', '')}", ""]
            continue
        if d.get("ky_vong"):
            ra += [f"**Kỳ vọng:** {d['ky_vong']}", ""]
        if d.get("loi"):
            ra += [f"**LỖI:** {d['loi']}", ""]
        ra += [f"**Trả lời:**\n\n{d.get('cau_tra_loi', '') or '(rỗng)'}", ""]
        ra += [f"**Nguồn:** {_mo_ta_nguon(d)}", ""]
        ra += [f"**Các bước:** `{d.get('buoc', [])}`", ""]
        ra += [
            "**Thời lượng:** " + " · ".join(f"{ten} {giay:.2f}s" for ten, giay in _thoi_luong(d)),
            "",
        ]
        thieu = "  ·  **THIẾU event `done`**" if d.get("co_done") is False else ""
        ra += [
            f"**Gợi ý tiếp theo:** {d.get('goi_y') or '—'}  ·  "
            f"**cho_trich_nguon:** {d.get('cho_trich_nguon')}  ·  "
            f"**{d.get('giay_tong', 0):.2f}s** (chữ đầu {d.get('giay_toi_chu_dau')}){thieu}",
            "",
        ]
    return ra


def _mo_ta_nguon(d: dict[str, Any]) -> str:
    nguon = d.get("nguon", [])
    if not nguon:
        return "—"
    return " · ".join(f"{n.get('title', '?')} (`{n.get('doc_id', '?')}`, {n.get('kind', '?')})" for n in nguon)


def dung_bang(goi: dict[str, Any]) -> str:
    rows = goi.get("ket_qua", [])
    chinh = [d for d in rows if not d.get("la_luot_xen")]
    dong = _phan_dau(goi)
    dong += _phan_do_tre(rows)
    dong += _phan_thoi_luong(rows)
    dong += [
        "## Tổng hợp",
        "",
        "Cột `truy hồi` đọc là `số đoạn @ độ phủ`. Cột `leo thang` là luật đã kích hoạt.",
        "",
        "| ID | Nhóm | Câu hỏi | Tool | Truy hồi | Leo thang | Nguồn | Giây | Trả lời (rút gọn) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    dong += [_dong_bang(d) for d in chinh]
    dong += ["", *_phan_toan_van(rows)]
    return "\n".join(dong) + "\n"
