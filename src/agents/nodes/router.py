"""Node phân loại câu hỏi (router).

Dùng model RẺ vì đây là bước nằm trên đường tới độ trễ cảm nhận của người dùng.
Có luật ưu tiên trước, chỉ gọi LLM khi luật không quyết được — vừa nhanh vừa rẻ.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState, Intent
from src.agents.thuc_the import lam_sach
from src.core.exceptions import SalesMateError
from src.core.logging import get_logger
from src.models.chat import ChatMessage, MessageRole

logger = get_logger(__name__)

_ROUTER_PROMPT = """Phân loại câu hỏi của người dùng vào ĐÚNG MỘT nhãn sau:

- general: CHỈ dùng cho xã giao — chào hỏi, cảm ơn, tạm biệt, tán gẫu ngoài
  chủ đề bất động sản. Người dùng không hỏi thông tin gì.
- document: cần tra tài liệu dự án — chính sách, ưu đãi, tiện ích, vị trí,
  tiến độ, tổng quan dự án
- listing: tìm bất động sản, tin đăng, so sánh căn
- price: hỏi giá, định giá, mặt bằng giá khu vực
- legal: thủ tục pháp lý, sổ đỏ, hợp đồng, thuế phí
- draft: nhờ soạn nội dung (tin đăng, tin nhắn cho khách)

QUAN TRỌNG: câu hỏi mơ hồ, cụt ngủn, thiếu tên dự án hay tiêu chí VẪN là câu
hỏi thông tin — chọn nhãn theo chủ đề, KHÔNG chọn general. "Ocean Park có ưu
đãi gì" là document, không phải general.

Chỉ trả về đúng một từ nhãn, không giải thích gì thêm.

Câu hỏi: {query}"""

# Luật nhanh: từ khoá rõ ràng thì khỏi tốn một lượt gọi LLM.
_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.LEGAL, ("sổ đỏ", "sổ hồng", "pháp lý", "thủ tục", "hợp đồng", "thuế", "sang tên")),
    (Intent.PRICE, ("giá", "bao nhiêu tiền", "định giá", "tr/m2", "tr/m²")),
    (Intent.DRAFT, ("viết tin", "soạn tin", "viết giúp", "soạn giúp", "tiêu đề tin")),
    (Intent.LISTING, ("tìm căn", "tìm nhà", "tìm mua", "căn hộ", "nhà phố", "đất nền")),
]


# Nhãn KHÔNG cần tra tài liệu. Khai theo hướng loại trừ, không phải liệt kê
# nhãn được phép — đảo chiều mặc định là chỗ sửa quan trọng nhất của node này.
#
# Trước đây `needs_retrieval` chỉ bật cho {DOCUMENT, LEGAL, PRICE}, nên `general`
# thành ngõ cụt tuyệt đối: không truy hồi, không tool, `plan` nhận state rỗng và
# nước duy nhất còn lại là hỏi ngược người dùng. Đo được trên câu thật: "Ocean
# park có ưu đãi gì" bị xếp `general` → trợ lý hỏi lại, trong khi truy hồi cho
# độ phủ 0.919 với đúng hai tài liệu ưu đãi OP2 và OP3.
#
# Nghịch lý của cách cũ: câu càng mơ hồ càng cần tra cứu thì càng bị từ chối tra
# cứu. Nay chỉ xã giao và soạn nội dung mới bỏ qua truy hồi; thêm nhãn mới về
# sau là tự động được tra cứu, tức là mặc định an toàn.
_KHONG_TRA_CUU = {Intent.GENERAL, Intent.DRAFT}


# Chỉ hỏi DANH TỪ, không hỏi ý định. Xem `src/agents/thuc_the.py` về lý do:
# kế thừa ý định từ lượt trước làm `dat_coc` ghi thêm lead ngoài ý muốn.
_THUC_THE_PROMPT = """Đọc lịch sử hội thoại rồi viết lại các TIÊU CHÍ mà câu hỏi mới
đang nhắc tới, kể cả khi nó dùng từ thay thế ("căn đó", "20 căn đó", "dự án vừa nói").

Lịch sử:
{lich_su}

Câu hỏi mới: {query}

Trả về ĐÚNG một object JSON, không giải thích, chỉ dùng các khoá sau khi thật sự
suy ra được (bỏ hẳn khoá không biết, KHÔNG điền null hay chuỗi rỗng):

  ma_can        mảng mã căn, dạng "VOP397"
  phan_khu      "Ocean Park 1" | "Ocean Park 2" | "Ocean Park 3"
  loai_can      ví dụ "2PN"
  huong         ví dụ "Đông Nam"
  gia_min       số, đơn vị TỶ đồng
  gia_max       số, đơn vị TỶ đồng
  dien_tich_min số, đơn vị m2
  dien_tich_max số, đơn vị m2
  von_tu_co     số, đơn vị TỶ đồng

Tuyệt đối không suy đoán tiêu chí mà hội thoại chưa hề nêu. Không có gì thì trả {{}}."""

# Chỉ lấy vài lượt gần nhất: tham chiếu ("căn đó") gần như luôn trỏ về lượt liền
# trước, còn nhét cả hội thoại dài vào vừa tốn token vừa cho model nhiều cơ hội
# lôi lại tiêu chí mà người dùng đã bỏ.
_SO_LUOT_NHIN_LAI = 4


def _tom_tat(history: list[ChatMessage]) -> str:
    return "\n".join(f"{m.role.value}: {m.content}" for m in history[-_SO_LUOT_NHIN_LAI:])


def _doc_json(raw: str) -> Any:
    """Đọc JSON model trả về, chịu được rào chữ ```json và chữ thừa hai đầu."""
    van_ban = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    dau, cuoi = van_ban.find("{"), van_ban.rfind("}")
    if dau == -1 or cuoi <= dau:
        return {}
    try:
        return json.loads(van_ban[dau : cuoi + 1])
    except json.JSONDecodeError:
        logger.warning("Thực thể không phải JSON hợp lệ, bỏ qua")
        return {}


class RouterNode(BaseNode):
    """Xác định intent và có cần truy hồi tài liệu không."""

    name = "router"

    def __init__(self, llm: LLMProvider, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def execute(self, state: AgentState) -> dict[str, Any]:
        query = state.get("query", "")
        intent = self._match_keywords(query) or await self._classify(query)
        return {
            "intent": intent,
            "needs_retrieval": intent not in _KHONG_TRA_CUU,
            "entities": await self._rut_thuc_the(query, state.get("history") or []),
        }

    def tom_tat(self, result: dict[str, Any]) -> str:
        nhan = result.get("intent")
        tra_cuu = "cần tra cứu" if result.get("needs_retrieval") else "không tra cứu"
        thuc_the = result.get("entities") or {}
        phan = f"nhãn={getattr(nhan, 'value', nhan)} · {tra_cuu}"
        if thuc_the:
            phan += f" · giải tham chiếu: {', '.join(sorted(thuc_the))}"
        return phan

    async def _rut_thuc_the(self, query: str, history: list[ChatMessage]) -> dict[str, Any]:
        """Giải tham chiếu bằng lịch sử. KHÔNG có lịch sử thì không gọi model.

        Điều kiện "có lịch sử" không phải để tiết kiệm tiền — với model rẻ thì
        một lượt gọi gần như không đáng kể. Nó để BẢO TOÀN hành vi: lượt đầu
        tiên vốn không có gì để giải tham chiếu, nên bỏ hẳn bước này thì đường
        một-lượt chạy y hệt trước khi có tính năng, và mọi con số đo cũ vẫn so
        sánh được.
        """
        if not history:
            return {}

        messages = [
            ChatMessage(
                role=MessageRole.USER,
                content=_THUC_THE_PROMPT.format(lich_su=_tom_tat(history), query=query),
            )
        ]
        try:
            raw = await self._llm.complete(messages, model=self._model, temperature=0.0, max_tokens=200)
        except SalesMateError as exc:
            # Rút thực thể là phần THÊM. Hỏng thì quay về hành vi cũ, không được
            # làm đứt lượt hỏi — tool vẫn còn regex trên câu hiện tại làm dự phòng.
            logger.warning("Rút thực thể hỏng, bỏ qua: %s", exc.code)
            return {}

        return lam_sach(_doc_json(raw))

    def _match_keywords(self, query: str) -> Intent | None:
        lowered = query.lower()
        for intent, keywords in _KEYWORD_RULES:
            if any(keyword in lowered for keyword in keywords):
                return intent
        return None

    async def _classify(self, query: str) -> Intent:
        messages = [ChatMessage(role=MessageRole.USER, content=_ROUTER_PROMPT.format(query=query))]
        raw = await self._llm.complete(messages, model=self._model, temperature=0.0, max_tokens=10)
        label = raw.strip().lower().strip(".")
        try:
            return Intent(label)
        except ValueError:
            logger.warning("Router trả nhãn lạ %r, rơi về general", label)
            return Intent.GENERAL
