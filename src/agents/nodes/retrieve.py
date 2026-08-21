"""Node truy hồi tài liệu.

Node này không biết gì về Qdrant hay embedding — nó chỉ gọi Retriever Protocol.
Đó là lý do module Data đổi thoải mái mà AI_core không phải sửa.
"""

from __future__ import annotations

from typing import Any

from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState, Intent
from src.agents.tools.search import _NGU_CANH_GIAO_DIEN
from src.data.contracts import RetrievalFilter
from src.models.chat import Citation
from src.rag.contracts import Retriever

# Nhãn nào thì chỉ nên đọc tài liệu chính sách, không đọc tin rao vặt.
#
# Vì sao cần: kho vector có 864 chunk tin rao ("Chính chủ cần bán…") và chỉ 66
# chunk chính sách. Hỏi "chính sách bán hàng chiết khấu" thì cả ba kết quả đầu
# đều là tin rao — chúng dùng chung từ vựng ("chính chủ", "bán", "thanh toán")
# và đông gấp 13 lần nên luôn thắng. Tài liệu tên đúng y câu hỏi không lọt nổi
# vào top.
#
# Độ phủ vẫn cao trong ca đó, nên guardrail không chặn: câu trả lời đi tiếp với
# ngữ cảnh sai và model đành nói "chưa đủ dữ liệu". Hỏng câm, không báo lỗi.
_CHI_DOC_CHINH_SACH = {Intent.LEGAL, Intent.DOCUMENT}


def _chi_lay_chinh_sach(state: AgentState) -> bool:
    """Có nên bó truy hồi vào tài liệu chính sách không.

    Hai điều kiện, cộng lại bằng OR:

    1. Nhãn vốn dĩ là hỏi tài liệu (`LEGAL`, `DOCUMENT`).
    2. **Tool đã cấp dữ liệu rồi.** Lúc đó việc còn lại của truy hồi là tìm QUY
       TẮC, không phải gom thêm tin rao — số liệu về căn đã có từ Postgres.

    Vế 2 sinh ra từ một ca hỏng thật: "tôi có 1 tỷ, mua căn VOP397 thì vay thế
    nào" bị xếp nhãn `price`, không thuộc vế 1, nên cả 5 đoạn truy hồi được đều
    là tin rao ("Cắt lỗ 2.680 tỷ căn 1PN…"). Chính sách hỗ trợ lãi suất nằm
    ngay trong kho nhưng không bao giờ tới tay model. Tệ hơn nữa: vì tool đã có
    giá nên guardrail không chặn, model trả lời với ngữ cảnh sai và tự bịa
    "ngân hàng cho vay 70-80% giá trị" — con số không có trong tài liệu nào.
    """
    return state.get("intent") in _CHI_DOC_CHINH_SACH or bool(state.get("tool_context"))


def _cau_de_truy_hoi(query: str) -> str:
    """Bỏ đuôi ngữ cảnh do WIDGET chèn trước khi đem đi nhúng vector.

    Đang mở một căn mà hỏi trống không thì FE gắn thêm "(căn đang xem: VOP437)"
    — xem `themNguCanh` trong ChatSidebar.jsx. Tool tra căn CẦN mã đó, nhưng
    truy hồi thì không: kho tài liệu chỉ có văn bản chính sách, không văn bản
    nào chứa mã căn. Đuôi này chỉ làm lệch vector.

    Hậu quả đã đo được trên production: cùng câu "Chính sách hỗ trợ lãi suất
    chung của Vinhomes" hỏi hai lần cho ra hai kết quả khác hẳn — một lần trả
    lời đầy đủ, một lần từ chối. Khác nhau đúng ở chỗ lượt kia đang mở một căn
    nên câu hỏi bị gắn thêm đuôi, nhúng ra vector khác, lấy về chunk khác.

    `InventorySearchTool` đã bỏ đuôi này từ trước vì cùng lý do; ở đây dùng lại
    đúng biểu thức đó để hai nơi không hiểu khác nhau.
    """
    sach = _NGU_CANH_GIAO_DIEN.sub(" ", query).strip()
    # Câu chỉ có mỗi đuôi ("phân tích căn này" -> rỗng sau khi bỏ) thì giữ
    # nguyên bản gốc, thà nhúng hơi lệch còn hơn nhúng chuỗi rỗng.
    return sach or query


class RetrieveNode(BaseNode):
    """Lấy chunk liên quan và tính độ phủ."""

    name = "retrieve"

    def __init__(self, retriever: Retriever, *, visibility: list[str] | None = None) -> None:
        self._retriever = retriever
        self._visibility = visibility or ["public"]

    async def execute(self, state: AgentState) -> dict[str, Any]:
        if not state.get("needs_retrieval"):
            return {"chunks": [], "coverage": 0.0, "context": ""}

        result = await self._retriever.retrieve(
            _cau_de_truy_hoi(state.get("query", "")),
            filters=RetrievalFilter(
                visibility=self._visibility,  # type: ignore[arg-type]
                doc_kind="policy" if _chi_lay_chinh_sach(state) else None,
            ),
        )

        return {
            "chunks": result.chunks,
            "coverage": result.coverage,
            "context": result.as_context(),
            # Đánh dấu ĐÃ tìm thật. `chunks` rỗng không nói lên điều đó: nó vừa
            # có nghĩa "tìm rồi mà không thấy" vừa có nghĩa "chưa hề tìm".
            # `plan` dựa vào cờ này để không hỏi ngược khi chưa tra cứu lần nào.
            "da_truy_hoi": True,
            "citations": [
                Citation(
                    doc_id=chunk.doc_id,
                    title=chunk.doc_title or chunk.doc_id,
                    version=chunk.version,
                    page=chunk.page,
                    section=chunk.section,
                    kind="doc",
                )
                for chunk in result.chunks
            ],
        }

    def tom_tat(self, result: dict[str, Any]) -> str:
        chunks = result.get("chunks") or []
        if not chunks:
            return "không truy hồi được đoạn nào"
        # Đếm số TÀI LIỆU riêng biệt chứ không chỉ số đoạn: 5 đoạn thường chỉ
        # đến từ 2-3 tài liệu, và nói "5 đoạn" khiến người đọc tưởng 5 nguồn.
        ten = {(c.doc_title or "?").strip() for c in chunks}
        return f"{len(chunks)} đoạn / {len(ten)} tài liệu · độ phủ {result.get('coverage', 0):.3f} · {', '.join(sorted(ten))[:70]}"
