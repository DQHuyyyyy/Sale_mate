"""Gọi vào SalesMate qua API và gom lại mọi thứ một lượt hỏi phát ra.

Vì sao gọi lõi AI (`:8001/api/v1/chat/stream`) chứ không gọi portal
(`:8000/api/chat`): portal chốt contract `{message, history} -> {reply}`, tức
chỉ còn CHỮ. Eval cần nhiều hơn thế — nguồn trích dẫn, tool nào đã chạy với
tham số gì, truy hồi được mấy đoạn và độ phủ bao nhiêu. Ngày 4 của plan phải
phân loại lỗi theo tầng (retrieval / generate / tool / guardrail), không có mấy
trường đó thì chỉ đoán được.

Vì sao dùng đường stream chứ không `/chat` một lần: các bước trung gian chỉ tồn
tại dưới dạng event `route`, bản không stream không phát. Đường stream cũng cho
đo được thời gian tới chữ đầu tiên, tách khỏi tổng thời gian.

Cũng vì vậy mà runner KHÔNG đi qua UI: automation giao diện vỡ mỗi lần đổi
layout, và vẫn không đọc được mấy trường trên.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DUONG_STREAM = "/api/v1/chat/stream"


@dataclass
class KetQuaLuot:
    """Toàn bộ dấu vết của một lượt hỏi."""

    cau_hoi: str
    cau_tra_loi: str = ""
    nguon: list[dict[str, Any]] = field(default_factory=list)
    buoc: list[dict[str, Any]] = field(default_factory=list)
    goi_y: list[Any] = field(default_factory=list)
    cho_trich_nguon: bool | None = None
    # Stream kết thúc mà KHÔNG có event `done` là một lỗi thật, không phải chi
    # tiết vặt: FE mất dãy nút gợi ý, và `cho_trich_nguon` thành `undefined` nên
    # widget rơi về hành vi cũ. Ghi thành cờ riêng để nó không lẫn vào `None`.
    co_done: bool = False
    # Nhãn cổng chính sách gán cho câu hỏi, và cổng có chặn hay không. Rỗng
    # nghĩa là cổng tắt, hoặc câu xã giao được bỏ qua không gọi model.
    chinh_sach_nhan: str = ""
    chinh_sach_chan: bool = False
    chinh_sach_ly_do: str = ""
    session_id: str = ""
    giay_toi_chu_dau: float | None = None
    giay_het_token: float | None = None
    giay_tong: float = 0.0
    loi: str = ""

    def moc_thoi_gian(self) -> list[tuple[str, float]]:
        """Thời điểm KẾT THÚC của từng bước, tính từ lúc gửi request.

        Lõi AI phát event `route` ngay sau khi mỗi node chạy xong
        (`_prepare_context` yield trong vòng lặp), nên thời điểm event tới nơi
        chính là lúc node đó xong. Trừ hai mốc liền nhau ra là thời lượng bước.

        ⚠️ Node KHÔNG phát event thì vô hình, thời gian của nó bị cộng vào bước
        hiện ngay sau. `_progress_events` im lặng khi router chưa có intent, khi
        không tool nào chạy, khi truy hồi rỗng, và khi cổng leo thang không mở.
        """
        moc = [(str(b.get("step", "?")), float(b.get("giay", 0.0))) for b in self.buoc]
        if self.giay_toi_chu_dau is not None:
            moc.append(("generate:chữ đầu", self.giay_toi_chu_dau))
        if self.giay_het_token is not None:
            moc.append(("generate:hết chữ", self.giay_het_token))
        moc.append(("done", self.giay_tong))
        return moc

    def tools_da_chay(self) -> list[str]:
        ra: list[str] = []
        for b in self.buoc:
            if b.get("step") in {"tools", "orchestrate"}:
                ra.extend(b.get("tools", []) or [])
        return list(dict.fromkeys(ra))

    def buoc_theo_ten(self, ten: str) -> dict[str, Any]:
        for b in self.buoc:
            if b.get("step") == ten:
                return b
        return {}


async def hoi(
    client: httpx.AsyncClient,
    base_url: str,
    cau_hoi: str,
    lich_su: list[dict[str, str]],
    session_id: str | None,
) -> KetQuaLuot:
    """Gửi một lượt, đọc hết SSE, trả về dấu vết đã gom."""
    kq = KetQuaLuot(cau_hoi=cau_hoi)
    than = {"message": cau_hoi, "history": lich_su, "session_id": session_id}
    bat_dau = time.perf_counter()
    try:
        async with client.stream("POST", base_url.rstrip("/") + DUONG_STREAM, json=than) as res:
            if res.status_code != httpx.codes.OK:
                await res.aread()
                kq.loi = f"HTTP {res.status_code}: {res.text[:300]}"
                return kq
            async for dong in res.aiter_lines():
                _nap_dong(kq, dong, bat_dau)
    except httpx.HTTPError as exc:
        kq.loi = f"{type(exc).__name__}: {exc}"
    kq.giay_tong = round(time.perf_counter() - bat_dau, 3)
    return kq


def _nap_dong(kq: KetQuaLuot, dong: str, bat_dau: float) -> None:
    """Bóc một dòng SSE. Dòng ping/comment và dòng rỗng bỏ qua."""
    if not dong.startswith("data:"):
        return
    tho = dong[len("data:") :].strip()
    if not tho:
        return
    try:
        su_kien = json.loads(tho)
    except json.JSONDecodeError:
        kq.loi = kq.loi or f"SSE không phải JSON: {tho[:120]}"
        return
    _nap_su_kien(kq, su_kien, bat_dau)


def _nap_su_kien(kq: KetQuaLuot, su_kien: dict[str, Any], bat_dau: float) -> None:
    loai = su_kien.get("type", "")
    kq.session_id = su_kien.get("session_id") or kq.session_id

    troi = round(time.perf_counter() - bat_dau, 3)

    if loai == "token":
        if kq.giay_toi_chu_dau is None:
            kq.giay_toi_chu_dau = troi
        kq.giay_het_token = troi
        kq.cau_tra_loi += su_kien.get("content", "")
    elif loai == "route":
        buoc = dict(su_kien.get("data", {}))
        buoc.setdefault("noi_dung", su_kien.get("content", ""))
        buoc["giay"] = troi
        kq.buoc.append(buoc)
    elif loai == "sources":
        kq.nguon = list(su_kien.get("citations", []))
    elif loai == "sensitive":
        # Cổng chính sách phát nhãn qua đây. Không ghi lại thì cờ `nhay_cam` vô
        # hình trong kết quả: nó KHÔNG chặn nên câu trả lời trông y hệt lượt
        # bình thường, và không có cách nào đo cổng gán nhãn đúng hay sai.
        data = su_kien.get("data", {})
        kq.chinh_sach_nhan = str(data.get("nhan", ""))
        kq.chinh_sach_chan = bool(data.get("chan"))
        kq.chinh_sach_ly_do = su_kien.get("content", "")
    elif loai == "done":
        kq.co_done = True
        data = su_kien.get("data", {})
        kq.goi_y = list(data.get("options", []) or [])
        kq.cho_trich_nguon = data.get("cho_trich_nguon")
    elif loai == "error":
        kq.loi = su_kien.get("content", "") or "lỗi không rõ"
