"""Chạy toàn bộ golden dataset qua SalesMate, ghi kết quả THÔ ra file.

Ngày 2 của plan: chỉ CHẠY và GHI LẠI, chưa chấm điểm. Tách hai việc ra là cố ý
— chấm điểm đổi rubric liên tục trong tuần, còn kết quả thô thì chạy một lần
tốn tiền model, phải giữ lại nguyên vẹn để chấm lại nhiều lần mà không phải hỏi
lại hệ thống.

    python -m eval.runner.chay                    # cả 29 câu
    python -m eval.runner.chay --chi T01,T03      # vài case
    python -m eval.runner.chay --nhom Tool-use    # một nhóm
    python -m eval.runner.chay --nhan truoc-fix   # đặt tên lần chạy

Chạy TUẦN TỰ, không song song: plan đo độ trễ P95, mà bắn song song thì các lượt
tranh nhau và con số đo được là của máy chứ không phải của hệ thống.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.runner import bang  # noqa: E402
from eval.runner.bo_cau_hoi import CauHoi, KichBan, doc_golden, gom_kich_ban, loc  # noqa: E402
from eval.runner.client import KetQuaLuot, hoi  # noqa: E402

GOC = Path(__file__).resolve().parents[2]
THU_MUC_KET_QUA = GOC / "eval" / "results"
BASE_URL_MAC_DINH = "http://localhost:8001"
TIMEOUT_GIAY = 180.0


async def chay_kich_ban(client: httpx.AsyncClient, base_url: str, kb: KichBan, kho: str) -> list[dict[str, Any]]:
    """Chạy hết các lượt của một kịch bản trong CÙNG một hội thoại."""
    session_id = uuid.uuid4().hex
    lich_su: list[dict[str, str]] = []
    ket_qua: list[dict[str, Any]] = []

    for cau in kb.cac_luot:
        bo_qua = cau.ly_do_bo_qua(kho)
        if bo_qua:
            ket_qua.append(_dong_bo_qua(cau, kb.ma, bo_qua))
            print(f"  {cau.ma}: BỎ QUA — {bo_qua[:90]}")
            continue

        for thu_tu, xen in enumerate(cau.luot_xen_truoc, 1):
            kq_xen = await hoi(client, base_url, xen, lich_su, session_id)
            _ghi_lich_su(lich_su, xen, kq_xen.cau_tra_loi)
            ket_qua.append(_dong_ket_qua(cau, kq_xen, kb.ma, la_luot_xen=True, thu_tu_xen=thu_tu))
            _in_dong(f"  (xen {thu_tu}) {xen[:48]}", kq_xen)

        kq = await hoi(client, base_url, cau.input_chay, lich_su, session_id)
        _ghi_lich_su(lich_su, cau.input_chay, kq.cau_tra_loi)
        ket_qua.append(_dong_ket_qua(cau, kq, kb.ma))
        _in_dong(f"  {cau.ma}: {cau.cau_hoi_xlsx[:52]}", kq)

    return ket_qua


def _ghi_lich_su(lich_su: list[dict[str, str]], cau_hoi: str, cau_tra_loi: str) -> None:
    lich_su.append({"role": "user", "content": cau_hoi})
    if cau_tra_loi.strip():
        lich_su.append({"role": "assistant", "content": cau_tra_loi})


def _in_dong(nhan: str, kq: KetQuaLuot) -> None:
    dau = "!" if kq.loi else "."
    tools = ",".join(kq.tools_da_chay()) or "-"
    print(f"{dau} {nhan:<60} {kq.giay_tong:>6.2f}s  tool={tools}  nguồn={len(kq.nguon)}")
    if kq.loi:
        print(f"    lỗi: {kq.loi[:200]}")


def _dong_ket_qua(
    cau: CauHoi,
    kq: KetQuaLuot,
    ma_kich_ban: str,
    la_luot_xen: bool = False,
    thu_tu_xen: int = 0,
) -> dict[str, Any]:
    dong = asdict(kq)
    dong.update(
        {
            "ma": f"{cau.ma}-xen{thu_tu_xen}" if la_luot_xen else cau.ma,
            "ma_kich_ban": ma_kich_ban,
            "nhom": cau.nhom,
            "loai": cau.loai,
            "do_kho": cau.do_kho,
            "luot": cau.luot,
            "la_luot_xen": la_luot_xen,
            "cau_hoi_xlsx": cau.cau_hoi_xlsx,
            "ky_vong": "" if la_luot_xen else cau.ky_vong,
            "cach_cham": "" if la_luot_xen else cau.cach_cham,
            "ghi_chu": cau.ghi_chu,
            "da_chay": True,
        }
    )
    return dong


def _dong_bo_qua(cau: CauHoi, ma_kich_ban: str, ly_do: str) -> dict[str, Any]:
    """Case chưa chạy được: vẫn có mặt trong bảng, kèm lý do."""
    return {
        "ma": cau.ma,
        "ma_kich_ban": ma_kich_ban,
        "nhom": cau.nhom,
        "loai": cau.loai,
        "do_kho": cau.do_kho,
        "luot": cau.luot,
        "la_luot_xen": False,
        "cau_hoi": cau.cau_hoi_xlsx,
        "cau_hoi_xlsx": cau.cau_hoi_xlsx,
        "ky_vong": cau.ky_vong,
        "cach_cham": cau.cach_cham,
        "ghi_chu": cau.ghi_chu,
        "da_chay": False,
        "ly_do_bo_qua": ly_do,
        "cau_tra_loi": "",
        "nguon": [],
        "buoc": [],
        "goi_y": [],
        "cho_trich_nguon": None,
        "session_id": "",
        "giay_toi_chu_dau": None,
        "giay_tong": 0.0,
        "loi": "",
    }


def _cau_hinh() -> dict[str, Any]:
    """Chụp lại cấu hình lúc chạy — báo cáo phải nói rõ đo trên hệ thống nào."""
    try:
        from src.core.config import get_settings

        s = get_settings()
    except Exception as exc:  # noqa: BLE001 - chỉ để ghi chú, không được chặn lần chạy
        return {"loi_doc_cau_hinh": f"{type(exc).__name__}: {exc}"}
    return {
        "app_env": str(s.app_env),
        "llm_model_answer": s.llm_model_answer,
        "llm_model_fast": s.llm_model_fast,
        "enable_rag": s.enable_rag,
        "retrieval_top_k": s.retrieval_top_k,
        "rerank_top_n": s.rerank_top_n,
        "reranker": s.reranker,
        "coverage_threshold": s.coverage_threshold,
        "enable_agent_loop": s.enable_agent_loop,
        "enable_orchestrator": s.enable_orchestrator,
        "orchestrator_model": s.orchestrator_model,
        "orchestrator_effort": s.orchestrator_effort,
        "che_do_leo_thang": s.che_do_leo_thang,
        # Cần cho bảng chi phí: cổng chạy bằng Sonnet nên nó là một khoản
        # Anthropic thật. Thiếu dòng này thì báo cáo tính thiếu ~40% chi phí mỗi
        # lượt mà không có dấu hiệu gì.
        "enable_cong_chinh_sach": s.enable_cong_chinh_sach,
        "cong_chinh_sach_model": s.cong_chinh_sach_model or s.orchestrator_model,
    }


def _commit() -> str:
    try:
        ra = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=GOC,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return "khong-ro"
    return ra.stdout.strip()


async def _chay_tat_ca(base_url: str, danh_sach: list[KichBan], kho: str) -> list[dict[str, Any]]:
    ket_qua: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT_GIAY) as client:
        for i, kb in enumerate(danh_sach, 1):
            print(f"[{i}/{len(danh_sach)}] kịch bản {kb.ma}")
            ket_qua.extend(await chay_kich_ban(client, base_url, kb, kho))
    return ket_qua


def _kiem_tra_server(base_url: str) -> str:
    try:
        res = httpx.get(base_url.rstrip("/") + "/api/v1/health", timeout=10.0)
    except httpx.HTTPError as exc:
        return f"Không gọi được lõi AI ở {base_url} ({exc}). Bật bằng: make run-ai"
    if res.status_code not in (200, 503):
        return f"Lõi AI trả HTTP {res.status_code} ở /api/v1/health"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy golden dataset qua SalesMate")
    parser.add_argument("--chi", default="", help="Chỉ chạy các mã này, cách nhau bằng dấu phẩy")
    parser.add_argument("--nhom", default="", help="Chỉ chạy một nhóm chỉ số, ví dụ: Tool-use")
    parser.add_argument("--nhan", default="", help="Nhãn lần chạy, đi vào tên file kết quả")
    parser.add_argument("--base-url", default=BASE_URL_MAC_DINH)
    parser.add_argument(
        "--kho",
        default="",
        help="Kho mà --base-url đang trỏ vào. Case khai kho riêng (A02) chỉ chạy khi khớp.",
    )
    args = parser.parse_args()

    loi = _kiem_tra_server(args.base_url)
    if loi:
        print(loi, file=sys.stderr)
        return 1

    danh_sach = loc(gom_kich_ban(doc_golden()), args.chi.split(",") if args.chi else None, args.nhom)
    if not danh_sach:
        print("Không có case nào khớp bộ lọc", file=sys.stderr)
        return 1

    moc = datetime.now().strftime("%Y%m%d-%H%M")
    ket_qua = asyncio.run(_chay_tat_ca(args.base_url, danh_sach, args.kho))
    goi = {
        "chay_luc": datetime.now().isoformat(timespec="seconds"),
        "commit": _commit(),
        "nhan": args.nhan,
        "base_url": args.base_url,
        "kho": args.kho,
        "cau_hinh": _cau_hinh(),
        "so_luot": len(ket_qua),
        "ket_qua": ket_qua,
    }

    ten = f"raw_{moc}" + (f"_{args.nhan}" if args.nhan else "")
    THU_MUC_KET_QUA.mkdir(parents=True, exist_ok=True)
    duong_json = THU_MUC_KET_QUA / f"{ten}.json"
    duong_json.write_text(json.dumps(goi, ensure_ascii=False, indent=2), encoding="utf-8")
    duong_md = THU_MUC_KET_QUA / f"{ten}.md"
    duong_md.write_text(bang.dung_bang(goi), encoding="utf-8")

    print(f"\nĐã ghi: {duong_json}")
    print(f"Đã ghi: {duong_md}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
