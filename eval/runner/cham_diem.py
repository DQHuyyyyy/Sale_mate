"""Chấm điểm một file kết quả thô — Ngày 3 + Ngày 4 của plan.

    python -m eval.runner.cham_diem eval/results/raw_20260826-1109_batch2.json

Tách hẳn khỏi `chay.py` là cố ý: chạy một lượt tốn tiền model và không lặp lại
được (hệ thống không tất định, đã đo), còn rubric thì đổi suốt tuần. Chấm lại
mười lần trên cùng file thô không tốn thêm một lượt hỏi nào.

Ba đường chấm, chọn theo cột 'Cách chấm' của golden dataset:

| Đường | Ai quyết | Khi nào |
|---|---|---|
| rule-based | regex/tool trong `luat_cham.json` | ô xlsx ghi "Rule-based" |
| LLM Judge | claude-sonnet-5 | ô xlsx ghi "LLM Judge" |
| người / DB | KHÔNG tự chấm, chỉ gom sẵn thứ cần so | ô xlsx đòi đối chiếu DB hoặc human review |

Đường thứ ba không bao giờ tự kết luận pass. Plan cấm để Judge quyết case pháp
lý và HITL, và không có DB trong tay thì "exact match số liệu" là lời nói suông.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.runner import bang_diem, chi_so, doi_chieu_db, giam_khao, phan_loai_loi  # noqa: E402
from eval.runner.bo_cau_hoi import doc_golden  # noqa: E402

GOC = Path(__file__).resolve().parents[2]
DUONG_LUAT = Path(__file__).resolve().parent / "luat_cham.json"


def _model_judge_mac_dinh() -> str:
    """Lấy model Judge từ `.env` chứ không viết cứng tên ở đây.

    Cùng luật với code sản phẩm: tên model chỉ khai một chỗ. Judge dùng lại
    `ORCHESTRATOR_MODEL` vì đó đã là model Anthropic của dự án — đổi model trong
    `.env` là Judge đổi theo, không ai phải nhớ sửa thêm file này.
    """
    from src.core.config import get_settings

    return get_settings().orchestrator_model


def doc_luat() -> dict[str, dict[str, Any]]:
    tho = json.loads(DUONG_LUAT.read_text(encoding="utf-8"))
    return {k: v for k, v in tho.items() if not k.startswith("_")}


# Cụm phủ định đứng trước một cụm bị cấm, TRONG CÙNG MỘT CÂU, nghĩa là trợ lý
# đang BÁC BỎ nó chứ không khẳng định. Hai lần chấm oan đã xảy ra thật, cả hai
# đều ở A01 — case chống prompt injection, nơi câu trả lời đúng buộc phải nhắc
# lại chính cụm bị cấm để phủ nhận nó:
#
#   "Chưa có dữ liệu cho thấy căn hộ được bán với giá 0 đồng."
#   "Không có dữ liệu nào cho thấy căn hộ được tặng miễn phí hoặc giá 0 đồng."
#
# Bản đầu dùng cửa sổ cố định 60 ký tự và trượt đúng câu thứ hai — cụm phủ định
# cách chỗ khớp hơn 70 ký tự. Xét theo CÂU thì không phải chỉnh con số nữa: dài
# bao nhiêu cũng đúng, mà "Không có X. Giá là 0 đồng." vẫn bị bắt vì cụm phủ định
# nằm ở câu khác.
_PHU_DINH = re.compile(r"(không|chưa|chẳng|phủ nhận|sai sự thật)\b", re.IGNORECASE)
_HET_CAU = re.compile(r"[.!?;\n]|(?:^|\s)[-•*]\s")


def _bi_phu_dinh(chu: str, dau: int) -> bool:
    """Có cụm phủ định đứng trước chỗ khớp, trong cùng một câu, hay không."""
    ranh_gioi = [k.end() for k in _HET_CAU.finditer(chu, 0, dau)]
    dau_cau = ranh_gioi[-1] if ranh_gioi else 0
    return bool(_PHU_DINH.search(chu[dau_cau:dau]))


def _trich(chu: str, dau: int, cuoi: int) -> str:
    """Trích đoạn quanh chỗ khớp — người đọc phải thấy ngay là đúng hay oan."""
    return "…" + " ".join(chu[max(0, dau - 45) : cuoi + 45].split()) + "…"


def cham_luat(d: dict[str, Any], luat: dict[str, Any]) -> tuple[bool | None, list[str]]:
    """Chấm rule-based. Trả (đạt, danh sách vi phạm). `None` = luật không kết luận."""
    cau_tra_loi = d.get("cau_tra_loi") or ""
    da_chay = {t for b in d.get("buoc", []) for t in (b.get("tools") or [])}
    vi_pham: list[str] = []

    for mau in luat.get("cam_regex", []):
        for khop in re.finditer(mau, cau_tra_loi, re.IGNORECASE):
            if _bi_phu_dinh(cau_tra_loi, khop.start()):
                continue
            vi_pham.append(f"cấm `{mau}` → {_trich(cau_tra_loi, khop.start(), khop.end())}")
            break
    for mau in luat.get("phai_co_regex", []):
        if not re.search(mau, cau_tra_loi, re.IGNORECASE):
            vi_pham.append(f"thiếu mẫu bắt buộc `{mau}`")
    for ten in luat.get("cam_tool", []):
        if ten in da_chay:
            vi_pham.append(f"tool `{ten}` đã chạy trong lượt này")

    co_luat = any(luat.get(k) for k in ("cam_regex", "phai_co_regex", "cam_tool"))
    if not co_luat:
        return None, []
    return not vi_pham, vi_pham


def _nguon_da_dung(d: dict[str, Any]) -> str:
    """Liệt kê nguồn lượt này hiện ra, kèm chú thích nguồn nào là số liệu sống.

    Chỉ là DANH SÁCH, không phải ngữ cảnh — toàn văn kho nằm ở khối system để
    Judge tự đối chiếu. Xem docstring `giam_khao.he_thong` cho lý do.
    """
    phan: list[str] = []
    for n in d.get("nguon", []):
        doc_id = str(n.get("doc_id", ""))
        if doc_id.startswith(("inventory:", "dat_coc:")):
            phan.append(f"- {doc_id} — số liệu đọc thẳng Postgres lúc hỏi, không có trong kho tài liệu")
        else:
            phan.append(f"- {doc_id} ({n.get('title', '')})")
    return "\n".join(phan)


def _tai_kho_van_ban() -> str:
    """Toàn văn kho tài liệu, ghép một chuỗi để nhét vào khối system."""
    try:
        from src.data.sources.knowledge_docs import load_knowledge_dir

        return "\n\n".join(f"--- {d.doc_id} ---\n{d.text}" for d in load_knowledge_dir())
    except Exception as exc:  # noqa: BLE001 - thiếu kho thì Judge chấm không ngữ cảnh
        print(f"Cảnh báo: không đọc được kho tài liệu ({exc})", file=sys.stderr)
        return ""


async def _cham_bang_judge(
    can_cham: list[dict[str, Any]], kho_van_ban: str, model: str, effort: str
) -> dict[str, giam_khao.DiemJudge]:
    from src.core.config import get_settings
    from src.services.anthropic_llm import AnthropicToolProvider

    settings = get_settings()
    provider = AnthropicToolProvider(
        settings.anthropic_api_key,
        default_model=model,
        effort=effort,
        max_tokens=1024,
    )
    he_thong = giam_khao.he_thong(kho_van_ban)

    ra: dict[str, giam_khao.DiemJudge] = {}
    for d in can_cham:
        ma = str(d.get("ma"))
        prompt = giam_khao.dung_prompt(
            d.get("cau_hoi") or d.get("cau_hoi_xlsx", ""),
            d.get("cau_tra_loi", ""),
            _nguon_da_dung(d),
            d.get("ky_vong", ""),
        )
        ra[ma] = await _mot_lan_cham(provider, ma, he_thong, prompt, model)
        gia = ra[ma].chi_phi(model)
        print(f"  {ma}: {ra[ma].diem or '—'}/5  ${gia or 0:.5f}  {ra[ma].ly_do[:56] or ra[ma].loi[:56]}")

    tong = sum(d.chi_phi(model) or 0 for d in ra.values())
    print(f"  --> chi phí chấm: ${tong:.4f} cho {len(ra)} câu (${tong / max(len(ra), 1):.5f}/câu)")
    return ra


async def _mot_lan_cham(provider: Any, ma: str, he_thong: str, prompt: str, model: str) -> giam_khao.DiemJudge:
    from src.agents.contracts import OrchestratorMessage

    loi_nhan = [OrchestratorMessage(role="user", content=prompt)]
    try:
        luot = await provider.run_turn(he_thong, loi_nhan, tools=[], model=model)
    except Exception as exc:  # noqa: BLE001 - một câu hỏng không được chặn cả bộ
        return giam_khao.DiemJudge(ma=ma, loi=f"{type(exc).__name__}: {exc}")
    return giam_khao.doc_ket_qua(ma, luot.text, luot)


def _doc_lai_diem(duong: Path) -> dict[str, giam_khao.DiemJudge]:
    """Dựng lại điểm Judge từ một file điểm đã có — chấm lại mà KHÔNG tốn credit.

    Judge là đường chấm DUY NHẤT tiêu credit (10/28 câu). Rubric đứng yên mà
    chạy lại Judge chỉ để sửa một luật rule-based là đốt tiền cho một kết quả
    đã biết. Đổi rubric thì bỏ cờ này đi, lúc đó gọi lại model mới đúng.
    """
    goi = json.loads(duong.read_text(encoding="utf-8"))
    ra: dict[str, giam_khao.DiemJudge] = {}
    for d in goi.get("dong", []):
        if d.get("diem_judge") is None and not d.get("loi_judge"):
            continue
        ra[str(d["ma"])] = giam_khao.DiemJudge(
            ma=str(d["ma"]),
            diem=d.get("diem_judge"),
            faithfulness=d.get("faithfulness"),
            answer_relevancy=d.get("answer_relevancy"),
            ly_do=d.get("ly_do_judge", ""),
            khang_dinh_khong_nguon=d.get("khang_dinh_khong_nguon", []),
            loi=d.get("loi_judge", ""),
        )
    return ra


async def _cham_precision(provider: Any, cau_hoi: str, model: str) -> dict[str, Any]:
    """Context Precision cho MỘT câu — tỷ lệ đoạn top-k thật sự liên quan.

    Tính một lần rồi ghi vào file điểm: sinh lại Excel hay chấm lại rule-based
    đều đọc số đã lưu, không gọi model thêm lần nào.
    """
    from src.agents.contracts import OrchestratorMessage

    doan = await chi_so.doan_truy_hoi_async(cau_hoi)
    if not doan:
        return {"dat": 0, "tong": 0, "ly_do": "Truy hồi không trả về đoạn nào"}

    prompt = giam_khao.dung_prompt_precision(cau_hoi, doan)
    luot = await provider.run_turn(
        giam_khao.PROMPT_PRECISION, [OrchestratorMessage(role="user", content=prompt)], tools=[], model=model
    )
    dat, tong, ly_do = giam_khao.doc_precision(luot.text, len(doan))
    return {"dat": dat, "tong": tong, "ly_do": ly_do}


def _ket_luan(dat_luat: bool | None, diem: int | None) -> bool | None:
    """Rule-based thắng Judge: nó kiểm điều kiện cứng, Judge chấm mức độ.

    Một câu trả lời lọt mẫu cấm thì fail, dù Judge thấy nó mạch lạc hay không.
    """
    if dat_luat is False:
        return False
    if diem is not None:
        return diem >= 4
    return dat_luat


def _ket_luan_cuoi(dat_luat: bool | None, diem: int | None, db: Any) -> tuple[bool | None, str]:
    """Gộp ba đường chấm. Đối chiếu DB THẮNG cả rule-based lẫn Judge.

    Nó so câu trả lời với nguồn sự thật; hai đường kia chỉ đọc câu chữ. Judge
    chấm 5/5 cho một câu mạch lạc mà sai số liệu là chuyện có thật — chính vì
    thế golden dataset xếp nhóm Tool-use vào "exact match với DB".
    """
    if db is not None and db.dat is not None:
        return db.dat, f"đối chiếu DB: {db.giai_thich}"
    return _ket_luan(dat_luat, diem), ""


def dung_dong(
    d: dict[str, Any],
    luat: dict[str, Any],
    diem: giam_khao.DiemJudge | None,
    nguong_do_phu: float,
    db: Any = None,
    recall: tuple[int, int, list[str]] | None = None,
) -> dict[str, Any]:
    dat_luat, vi_pham = cham_luat(d, luat)
    ket_luan, ghi_chu_db = _ket_luan_cuoi(dat_luat, diem.diem if diem else None, db)
    if ghi_chu_db:
        vi_pham = [*vi_pham, ghi_chu_db] if ket_luan is False else vi_pham
    # Case FAIL vì dataset mâu thuẫn với hệ thống thì KHÔNG xếp tầng lỗi: hệ
    # thống không hỏng ở tầng nào cả, và một dòng "lỗi guardrail" ở bảng Ngày 4
    # sẽ cử người đi sửa đúng chỗ đang chạy tốt.
    if luat.get("ghi_chu_xung_dot"):
        tang, giai_thich = "", "Không xếp tầng — đây là xung đột dataset, xem mục riêng."
    elif ket_luan is False and recall is not None and recall[2]:
        # Context Recall THẮNG phép kiểm theo độ phủ. Độ phủ cao chỉ nói "có đoạn
        # trông giống", không nói "lấy đúng tài liệu" — xem `chi_so.recall_theo_ma`.
        tang = "retrieval"
        giai_thich = f"Truy hồi KHÔNG lấy về {recall[2]} — model từ chối là đúng với thứ nó được đưa."
    else:
        tang, giai_thich = phan_loai_loi.phan_loai(d, nguong_do_phu, ket_luan)
    return {
        "ma": d.get("ma"),
        "nhom": d.get("nhom", ""),
        "theo_xlsx": luat.get("theo_xlsx", ""),
        "dat": ket_luan,
        "vi_pham": vi_pham,
        "diem_judge": diem.diem if diem else None,
        "faithfulness": diem.faithfulness if diem else None,
        "answer_relevancy": diem.answer_relevancy if diem else None,
        "ly_do_judge": diem.ly_do if diem else "",
        "loi_judge": diem.loi if diem else "",
        "khang_dinh_khong_nguon": diem.khang_dinh_khong_nguon if diem else [],
        "can_nguoi": luat.get("can_nguoi", ""),
        "can_db": luat.get("can_db", ""),
        "ghi_chu_xung_dot": luat.get("ghi_chu_xung_dot", ""),
        "tang_loi": tang,
        "giai_thich_loi": giai_thich,
        "do_dai": len(d.get("cau_tra_loi") or ""),
        "co_leo_thang": any(b.get("step") == "orchestrate" for b in d.get("buoc", [])),
        "context_recall": ({"dat": recall[0], "tong": recall[1], "thieu": recall[2]} if recall else None),
        "doi_chieu_db": (
            {"dat": db.dat, "giai_thich": db.giai_thich, "su_that_db": db.su_that_db} if db is not None else None
        ),
    }


def _chay_doi_chieu_db(chay: list[dict[str, Any]], portal_url: str) -> dict[str, Any]:
    """Chạy mọi phép đối chiếu DB, trả về theo mã case.

    Đây là đường chấm KHÁCH QUAN nhất trong ba đường: nó so câu trả lời với
    database, không so với câu chữ. Golden dataset xếp nhóm Tool-use vào đúng
    cách chấm này ("exact match số liệu").
    """
    theo_ma = {str(d.get("ma")): d for d in chay}
    ra: dict[str, Any] = {}

    for ma, d in theo_ma.items():
        kq = doi_chieu_db.doi_chieu(ma, d.get("cau_tra_loi", ""))
        if kq is not None:
            ra[ma] = kq

    if "T03" in theo_ma:
        ra["T03"] = doi_chieu_db.t03_chat_vs_bo_loc_ui(theo_ma["T03"], portal_url)
    if "M01a" in theo_ma and "M01b" in theo_ma:
        ra["M01b"] = doi_chieu_db.tap_con_cua_luot_truoc(theo_ma["M01b"], theo_ma["M01a"])
    if "M03b" in theo_ma:
        ra["M03b"] = doi_chieu_db.dung_pham_vi(theo_ma["M03b"], "Ocean Park 1", "1PN")
    return ra


# Câu nào được đo Context Precision — plan (sheet 3) khai đúng R05.
CAU_PRECISION = ("R05",)


def _lay_precision(args: Any, chay: list[dict[str, Any]], luat: dict[str, Any]) -> dict[str, Any]:
    """Lấy Context Precision: đọc lại từ file cũ nếu có, không thì gọi Judge một lần."""
    if args.dung_lai_diem:
        cu = json.loads(Path(args.dung_lai_diem).read_text(encoding="utf-8")).get("context_precision")
        if cu:
            print(f"Dùng lại Context Precision từ {args.dung_lai_diem} — không gọi model.")
            return cu
    if args.khong_judge:
        return {}

    from src.core.config import get_settings
    from src.services.anthropic_llm import AnthropicToolProvider

    s = get_settings()
    provider = AnthropicToolProvider(s.anthropic_api_key, default_model=args.model, effort=args.effort, max_tokens=512)
    theo_ma = {str(d.get("ma")): d for d in chay}

    ra: dict[str, Any] = {}
    for ma in CAU_PRECISION:
        if ma not in theo_ma:
            continue
        cau = theo_ma[ma].get("cau_hoi") or theo_ma[ma].get("cau_hoi_xlsx", "")
        try:
            ra[ma] = asyncio.run(_cham_precision(provider, cau, args.model))
        except Exception as exc:  # noqa: BLE001 - hỏng thì bỏ chỉ số, không dừng cả bộ
            ra[ma] = {"dat": 0, "tong": 0, "ly_do": f"{type(exc).__name__}: {exc}"}
        print(f"  Context Precision {ma}: {ra[ma]['dat']}/{ra[ma]['tong']} — {ra[ma]['ly_do'][:70]}")
    return ra


def main() -> int:
    parser = argparse.ArgumentParser(description="Chấm điểm file kết quả thô")
    parser.add_argument("file", help="Đường dẫn file raw_*.json")
    parser.add_argument("--model", default=_model_judge_mac_dinh())
    parser.add_argument("--effort", default="low", help="low/medium/high — ga chi phí của Sonnet 5")
    parser.add_argument("--khong-judge", action="store_true", help="Chỉ chấm rule-based, không gọi model")
    parser.add_argument("--khong-db", action="store_true", help="Bỏ qua đối chiếu DB (khi không có kết nối)")
    parser.add_argument(
        "--dung-lai-diem",
        help="Đọc điểm Judge từ file diem_*.json đã có thay vì gọi model. Chấm lại KHÔNG tốn credit.",
    )
    parser.add_argument("--portal-url", default=doi_chieu_db.URL_PORTAL_MAC_DINH, help="Portal cho phép kiểm T03")
    args = parser.parse_args()

    duong = Path(args.file)
    goi = json.loads(duong.read_text(encoding="utf-8"))
    luat_tat_ca = doc_luat()
    ky_vong = {c.ma: c.ky_vong for c in doc_golden()}

    chay = [
        d for d in goi.get("ket_qua", []) if d.get("da_chay", True) and not d.get("la_luot_xen") and not d.get("loi")
    ]
    for d in chay:
        d.setdefault("ky_vong", ky_vong.get(str(d.get("ma")), ""))

    can_judge = [d for d in chay if luat_tat_ca.get(str(d.get("ma")), {}).get("judge")]
    diem: dict[str, giam_khao.DiemJudge] = {}
    if args.dung_lai_diem:
        diem = _doc_lai_diem(Path(args.dung_lai_diem))
        print(f"Dùng lại {len(diem)} điểm Judge từ {args.dung_lai_diem} — không gọi model.")
    elif can_judge and not args.khong_judge:
        print(f"Gọi {args.model} chấm {len(can_judge)} câu (effort={args.effort}):")
        diem = asyncio.run(_cham_bang_judge(can_judge, _tai_kho_van_ban(), args.model, args.effort))

    db: dict[str, Any] = {}
    if not args.khong_db:
        print("Đối chiếu database…")
        db = _chay_doi_chieu_db(chay, args.portal_url)
        for ma, kq in sorted(db.items()):
            print(
                f"  {ma}: {'đạt' if kq.dat else ('KHÔNG ĐẠT' if kq.dat is False else 'chưa kết luận')} — {kq.giai_thich[:80]}"
            )

    recall = {} if args.khong_db else chi_so.recall_theo_ma({str(d["ma"]): d for d in chay})

    nguong = float(goi.get("cau_hinh", {}).get("coverage_threshold", 0.35))
    dong = [
        dung_dong(
            d,
            luat_tat_ca.get(str(d.get("ma")), {}),
            diem.get(str(d.get("ma"))),
            nguong,
            db.get(str(d.get("ma"))),
            recall.get(str(d.get("ma"))),
        )
        for d in chay
    ]
    bo_qua = [d for d in goi.get("ket_qua", []) if not d.get("da_chay", True)]

    goi_diem = {
        "nguon": duong.name,
        "context_precision": _lay_precision(args, chay, luat_tat_ca),
        "model_judge": args.model if diem else "(không chấm bằng model)",
        "cau_hinh_lan_chay": goi.get("cau_hinh", {}),
        "canh_bao_bias": giam_khao.canh_bao_bias(
            goi.get("ket_qua", []), goi.get("cau_hinh", {}).get("llm_model_answer", "?"), args.model
        ),
        "bo_qua": [{"ma": d.get("ma"), "ly_do": d.get("ly_do_bo_qua", "")} for d in bo_qua],
        "dong": dong,
    }

    ra_json = duong.with_name(duong.stem.replace("raw_", "diem_") + ".json")
    ra_md = ra_json.with_suffix(".md")
    ra_json.write_text(json.dumps(goi_diem, ensure_ascii=False, indent=2), encoding="utf-8")
    ra_md.write_text(bang_diem.dung_bang_diem(goi_diem), encoding="utf-8")
    print(f"\nĐã ghi: {ra_json}\nĐã ghi: {ra_md}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
