"""Phân loại lỗi theo TẦNG — Ngày 4 của plan.

Tất định, không gọi model. Mọi tín hiệu cần thiết đã nằm trong file kết quả thô:
tool nào chạy với tham số gì, truy hồi mấy đoạn với độ phủ bao nhiêu, còn mấy
nguồn sau khi lọc. Hỏi model để phân loại lại thứ đã đo được là thêm một nguồn
bất định vào đúng bước cần chắc chắn nhất — hai lần chạy bộ chấm sẽ ra hai bảng
nguyên nhân khác nhau, và không ai biết tin bảng nào.

Bốn tầng lấy đúng theo plan: retrieval · generate · tool · guardrail.
"""

from __future__ import annotations

from typing import Any

TU_CHOI = "chưa có đủ dữ liệu"


def _buoc(d: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {b.get("step", ""): b for b in d.get("buoc", [])}


def _la_tu_choi(d: dict[str, Any]) -> bool:
    return TU_CHOI in (d.get("cau_tra_loi") or "").lower()


def phan_loai(d: dict[str, Any], nguong_do_phu: float, dat: bool | None) -> tuple[str, str]:
    """Trả (tầng, giải thích). Tầng rỗng nghĩa là không phân loại được lỗi nào.

    Chỉ phân loại khi case đã FAIL. Case pass mà đi truy nguyên nhân thì bảng
    Ngày 4 đầy những dòng không ai phải làm gì với chúng.
    """
    if dat is not False:
        return "", ""

    b = _buoc(d)
    can_tra_cuu = bool(b.get("router", {}).get("needs_retrieval"))
    co_tool = bool(b.get("tools", {}).get("found"))
    chunks = int(b.get("retrieve", {}).get("chunks", 0) or 0)
    do_phu = float(b.get("retrieve", {}).get("coverage", 0.0) or 0.0)

    if can_tra_cuu and "tools" not in b and not chunks:
        return (
            "tool",
            "Nhãn cần tra cứu nhưng không tool nào nhận và truy hồi cũng rỗng — `build_args` không rút được tiêu chí.",
        )
    if _la_tu_choi(d) and (co_tool or do_phu >= nguong_do_phu):
        # KHÔNG phải guardrail. `GuardrailNode` chỉ thay câu trả lời khi
        # `needs_retrieval` mà bằng chứng KHÔNG đủ; đủ bằng chứng thì nó để
        # nguyên. Nên một câu từ chối khi độ phủ đã vượt ngưỡng là do chính
        # `generate` viết ra — model cầm tài liệu trong tay mà vẫn nói không có.
        # Xếp nhầm sang guardrail là cử người đi chỉnh ngưỡng độ phủ, trong khi
        # chỗ phải sửa là prompt.
        return (
            "generate",
            f"Model tự từ chối dù bằng chứng đã đủ (tool={co_tool}, độ phủ={do_phu} ≥ {nguong_do_phu}) "
            "— guardrail không can thiệp ở mức độ phủ này.",
        )
    if not _la_tu_choi(d) and can_tra_cuu and not co_tool and do_phu < nguong_do_phu:
        return "guardrail", f"Trả lời dù độ phủ {do_phu} dưới ngưỡng {nguong_do_phu} và không có dữ liệu tool."
    if can_tra_cuu and not co_tool and do_phu < nguong_do_phu:
        return "retrieval", f"Độ phủ {do_phu} dưới ngưỡng {nguong_do_phu}, truy hồi {chunks} đoạn không đủ liên quan."
    if co_tool or chunks:
        return "generate", "Bằng chứng đã có trong state nhưng câu trả lời không dùng đúng."
    return "", "Chưa xếp được tầng — cần xem tay."


def gom_theo_tang(dong: list[dict[str, Any]]) -> dict[str, list[str]]:
    gom: dict[str, list[str]] = {}
    for d in dong:
        tang = d.get("tang_loi") or ""
        if tang:
            gom.setdefault(tang, []).append(str(d.get("ma", "?")))
    return gom
