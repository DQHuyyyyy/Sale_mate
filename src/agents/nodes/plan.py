"""Node lập kế hoạch — nơi agent tự quyết làm gì tiếp theo.

Đây là thứ biến hệ thống từ "pipeline RAG có tool" thành agent thật: model nhìn
câu hỏi cùng những gì đã thu được, rồi chọn một trong ba hành động. Chạy lại sau
mỗi lần hành động, nên nó vừa là bước quan sát vừa là bước quyết định — đúng
kiểu observe-then-decide, không tách thành hai node cho một việc.

    act       gọi thêm một tool để lấy dữ kiện còn thiếu
    retrieve  đi tra kho tài liệu trước khi kết luận
    clarify   câu hỏi mơ hồ, hỏi lại người dùng thay vì đoán
    answer    đã đủ, chuyển sang sinh câu trả lời

Bốn thứ giữ cho nó không chạy loạn:

1. **Trần cứng.** Hết `agent_max_iterations` là ép `answer`, model không có
   quyền xin thêm. Thiếu cái này thì một câu hỏi xấu gọi tool đến hết quota.
2. **Không gọi được tool lạ.** Tên tool model trả về phải có trong registry,
   sai thì rơi về `answer` chứ không thử đoán.
3. **Không lặp lại chính mình.** Hành động trùng với thứ đã thử là dấu hiệu
   agent kẹt — gọi lại cũng ra kết quả cũ, nên cắt sớm thay vì đốt nốt trần.
4. **Không bỏ cuộc khi chưa tra cứu.** Ba chốt trên đều chặn agent làm QUÁ
   NHIỀU; chốt này chặn nó làm quá ít. Xem `_phai_tra_cuu_truoc`.

`LLMProvider` là contract đóng băng và không có API tool-calling, nên plan yêu
cầu model trả JSON qua `complete()` rồi tự parse — cùng cách RouterNode lấy nhãn.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.agents.contracts import LLMProvider
from src.agents.nodes.act import _chu_ky, _lam_sach
from src.agents.nodes.base import BaseNode
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.logging import get_logger

logger = get_logger(__name__)

ACT = "act"
ANSWER = "answer"
CLARIFY = "clarify"
RETRIEVE = "retrieve"

# Số phương án chọn sẵn tối đa kèm một câu hỏi ngược. Nhiều hơn thì người dùng
# phải đọc thay vì bấm, mất luôn ý nghĩa của việc gợi sẵn.
_TOI_DA_PHUONG_AN = 4

_PROMPT = """Bạn là bộ điều phối của trợ lý bán căn hộ. Chọn ĐÚNG MỘT hành động tiếp theo.

Câu hỏi của người dùng:
{query}

Dữ kiện đã thu thập được:
{evidence}

Các tool có thể gọi:
{tools}

Hành động cho phép:
- "act": còn thiếu dữ kiện và có tool lấy được. Phải nêu "tool" và "args".
- "clarify": ĐÃ tra cứu nhưng dữ kiện phủ nhiều khả năng khác nhau, cần người
  dùng chọn. Nêu câu hỏi ngược ở "reason" và các phương án ở "options".
- "answer": đã đủ dữ kiện, hoặc không tool nào giúp được, HOẶC người dùng chỉ
  đang xã giao (chào hỏi, cảm ơn, tạm biệt) — lúc đó cứ đáp lời, đừng hỏi ngược.

Về "options" (chỉ dùng với "clarify", và chỉ khi CHƯA có tài liệu nào ở phần
dữ kiện): tối đa {toi_da} chuỗi, mỗi chuỗi là một CỤM DANH TỪ ngắn gọn chỉ chủ
đề người dùng có thể chọn — ví dụ "Ưu đãi Ocean Park 2", KHÔNG viết thành câu
hỏi đóng kiểu "Bạn có muốn biết ưu đãi Ocean Park 2 không?".

Chỉ nêu thứ CÓ THẬT trong dữ kiện. Đừng liệt kê phương án mà bạn không thấy dữ
liệu nào chứng minh là tồn tại.

Trả về DUY NHẤT một object JSON, không giải thích, không bọc trong markdown:
{{"action": "...", "tool": "...", "args": {{}}, "options": [], "reason": "một câu ngắn bằng tiếng Việt"}}"""

# Model hay bọc JSON trong ```json ... ``` dù đã dặn đừng.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# Mã căn trong câu hỏi, dùng cho luật "còn thiếu mã nào thì đi lấy".
_MA_CAN = re.compile(r"\b[A-Za-z]{2,4}\d{2,5}\b")
# Tên tool tra theo mã căn. Có nhắc tên cụ thể ở đây, nhưng luôn hỏi registry
# trước khi dùng — thiếu tool thì rơi về để model tự quyết, không nổ.
_TOOL_TRA_MA_CAN = "inventory_lookup"


def _phuong_an_tu_tai_lieu(state: AgentState) -> list[str]:
    """Phương án lấy thẳng TÊN TÀI LIỆU đã truy hồi, không hỏi model.

    Vì sao không để model tự nghĩ: nó gợi ý thứ không tồn tại. Ca thật — kho chỉ
    có ưu đãi của Ocean Park 2 và 3, model vẫn chào "ưu đãi của Ocean Park 1".
    Người dùng bấm vào, agent tra không ra, lại hỏi ngược tiếp; hai lượt trôi đi
    mà không ai tiến thêm bước nào.

    Tên tài liệu là danh sách những gì THẬT SỰ có, đã xếp theo độ liên quan.
    Cùng lý lẽ với `_ma_can_con_thieu`: câu hỏi có đáp án khách quan thì đối
    chiếu dữ liệu, đừng đưa cho model đoán.

    Chúng cũng sẵn là cụm danh từ ("Ưu đãi của Vinhomes OceanPark 2"), đọc như
    một gợi ý bấm được — hơn hẳn câu hỏi đóng "Bạn có muốn biết… không?" mà
    bấm vào chỉ như đang trả lời "có".
    """
    ten = [(c.doc_title or "").strip() for c in state.get("chunks") or []]
    return list(dict.fromkeys(t for t in ten if t))[:_TOI_DA_PHUONG_AN]


def _doc_phuong_an(data: dict[str, Any]) -> list[str]:
    """Lọc phương án model trả về — chỉ dùng khi KHÔNG có tài liệu nào.

    Đường dự phòng cho ca clarify sau khi chạy tool: lúc đó không có tên tài
    liệu nào để bám, đành nhận đề xuất của model. Model hay trả lẫn `null`, số,
    hoặc object; một phần tử rác làm hỏng cả dãy nút nên lọc ở đây.
    """
    tho = data.get("options")
    if not isinstance(tho, list):
        return []
    sach = [t.strip() for t in tho if isinstance(t, str) and t.strip()]
    return list(dict.fromkeys(sach))[:_TOI_DA_PHUONG_AN]


def _gia_tri_cho_phep(o: dict[str, Any]) -> list[str]:
    """Danh sách giá trị hợp lệ của một trường, nếu schema có khai.

    Trường Optional được pydantic mô tả bằng `anyOf: [{...}, {"type": "null"}]`,
    nên phải chui vào trong mới thấy `enum`.
    """
    if o.get("enum"):
        return [str(v) for v in o["enum"]]
    for nhanh in o.get("anyOf") or []:
        if nhanh.get("enum"):
            return [str(v) for v in nhanh["enum"]]
    return []


def _kieu(o: dict[str, Any]) -> str:
    if o.get("type"):
        return str(o["type"])
    kieu = [str(n["type"]) for n in (o.get("anyOf") or []) if n.get("type") and n["type"] != "null"]
    return kieu[0] if kieu else ""


def _mo_ta_tham_so(schema: dict[str, Any]) -> str:
    """Mô tả từng tham số kèm KIỂU, GIÁ TRỊ HỢP LỆ và giải thích.

    Bản đầu chỉ liệt kê tên tham số, vứt hết phần còn lại của JSON Schema. Model
    thấy có trường tên `sort`, không biết nó nhận giá trị gì, nên điền `"price"`
    — suy đoán hợp lý nhất có thể. Pydantic từ chối và cả tool hỏng.
    Đó là lỗi thiết kế phía ta: đưa tờ khai không có nhãn ô rồi trách người điền
    sai. `SearchArgs` vốn đã khai đủ Literal và description, chỉ là không ai
    chuyển tiếp cho model.
    """
    props = schema.get("properties") or {}
    if not props:
        return "    (không có tham số)"

    bat_buoc = set(schema.get("required") or [])
    dong = []
    for ten, o in props.items():
        phan = [f"    - {ten}"]
        gia_tri = _gia_tri_cho_phep(o)
        if gia_tri:
            phan.append(f"(chỉ nhận: {' | '.join(gia_tri)})")
        elif kieu := _kieu(o):
            phan.append(f"({kieu})")
        if ten in bat_buoc:
            phan.append("[bắt buộc]")
        if mo_ta := o.get("description"):
            phan.append(f"— {mo_ta}")
        dong.append(" ".join(phan))
    return "\n".join(dong)


def _describe_tools(registry: ToolRegistry) -> str:
    lines = []
    for tool in registry.all():
        schema = (tool.args_schema.model_json_schema() if tool.args_schema else {}) or {}
        lines.append(f"- {tool.name}: {tool.description}\n  Tham số:\n{_mo_ta_tham_so(schema)}")
    return "\n".join(lines) or "(không có tool nào)"


def _describe_evidence(state: AgentState) -> str:
    parts = []
    if state.get("tool_context"):
        parts.append(f"Từ tool:\n{state['tool_context']}")

    chunks = state.get("chunks") or []
    if chunks:
        # Nêu TÊN tài liệu, không chỉ đếm số đoạn. Chỉ nói "5 đoạn đã truy hồi"
        # thì model không biết chúng nói về cái gì, nên khi phải hỏi ngược nó
        # bịa ra trục lựa chọn — hỏi "loại ưu đãi nào?" trong khi trục mơ hồ
        # thật là Ocean Park 2 hay 3. Có tên tài liệu là nó thấy đúng trục.
        ten = list(dict.fromkeys(c.doc_title or c.doc_id for c in chunks))
        parts.append(
            "Từ tài liệu, {} đoạn thuộc các tài liệu:\n{}".format(len(chunks), "\n".join(f"- {t}" for t in ten))
        )

    return "\n\n".join(parts) or "(chưa có gì)"


class PlanNode(BaseNode):
    """Chọn hành động tiếp theo cho agent."""

    name = "plan"

    def __init__(
        self,
        llm: LLMProvider,
        *,
        max_iterations: int,
        model: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._llm = llm
        self._max_iterations = max_iterations
        self._model = model
        self._registry = registry or default_registry

    async def execute(self, state: AgentState) -> dict[str, Any]:
        iterations = int(state.get("iterations", 0))

        if iterations >= self._max_iterations:
            logger.info("Hết trần %s vòng, ép trả lời", self._max_iterations)
            return self._quyet(ANSWER, "Đã đủ số lần tra cứu cho phép.")

        thieu = self._ma_can_con_thieu(state)
        if thieu is not None:
            return thieu

        # CỐ Ý KHÔNG có đường tắt kiểu "tool tất định đã chạy ⇒ trả lời luôn".
        # Từng có, và nó vô hiệu hoá chính vòng lặp: "so sánh căn VOP345 và
        # VOP397" thì ToolsNode chỉ bắt được mã đầu tiên, plan thấy đã có dữ
        # liệu nên dừng — trả lời về một căn rồi im, không bao giờ tra căn thứ
        # hai. Đổi lại mỗi câu hỏi tốn một lượt gọi model rẻ; đó là giá của việc
        # để agent tự quyết, và chỉ phải trả khi `enable_agent_loop` bật.
        raw = await self._llm.complete([self._prompt(state)], model=self._model, temperature=0.0, max_tokens=200)
        return self._doc_ket_qua(raw, state)

    def _ma_can_con_thieu(self, state: AgentState) -> dict[str, Any] | None:
        """Câu hỏi nhắc mã căn nào mà bằng chứng chưa có thì đi lấy, KHÔNG hỏi model.

        Vì sao không để model quyết: nó tự nhận nhầm là đã đủ. Ca thật đã gặp —
        "so sánh VOP217 và VOP902", tool tất định chỉ bắt được mã đầu, nhưng
        plan trả lời "Đã có đủ thông tin để so sánh VOP217 và VOP902" trong khi
        bằng chứng chỉ có VOP217. Người dùng nhận câu từ chối, hỏi lại ba lần
        vẫn vậy.

        "Đã có mã X trong bằng chứng chưa" là câu hỏi có đáp án khách quan, đối
        chiếu chuỗi là xong — không cần và không nên phụ thuộc phán đoán model.
        """
        tool = self._registry.get(_TOOL_TRA_MA_CAN)
        if tool is None:
            return None  # Không có tool tra mã căn thì để model tự xoay.

        da_co = state.get("tool_context", "").upper()
        da_thu = set(state.get("da_thu", []))

        for ma in dict.fromkeys(m.upper() for m in _MA_CAN.findall(state.get("query", ""))):
            if ma in da_co:
                continue
            args = {"unit_code": ma}
            if _chu_ky(_TOOL_TRA_MA_CAN, args) in da_thu:
                continue  # Đã tra rồi mà không ra — đừng lặp.
            logger.info("Câu hỏi nhắc %s nhưng chưa có dữ liệu, tra thêm", ma)
            return self._quyet(ACT, f"Cần tra thêm thông tin căn {ma}.", tool=_TOOL_TRA_MA_CAN, args=args)

        return None

    @staticmethod
    def _phai_tra_cuu_truoc(state: AgentState) -> bool:
        """Đòi hỏi ngược khi chưa hề tra cứu ⇒ bắt đi tra trước.

        Chốt thứ tư, và là chốt duy nhất chặn agent BỎ CUỘC quá sớm.

        Ca thật: "Ocean park có ưu đãi gì" bị router xếp `general` nên node
        retrieve không chạy. `plan` nhìn vào state rỗng, không có gì để cân
        nhắc, nên chọn `clarify` — rồi bịa luôn trục mơ hồ, hỏi "loại ưu đãi
        nào?" trong khi trục thật là Ocean Park 2 hay 3. Truy hồi cho độ phủ
        0.919 với đúng hai tài liệu đó, agent chỉ là chưa bao giờ nhìn.

        Hỏi ngược mà chưa có bằng chứng thì đoán mò chỗ cần làm rõ. Một lần
        truy hồi rẻ hơn nhiều so với việc bắt người dùng mất một lượt.

        Chỉ ép ĐÚNG MỘT LẦN: `da_truy_hoi` do node retrieve bật, nên vòng sau
        điều kiện này sai và `clarify` đi tiếp bình thường — kể cả khi tra
        xong vẫn không ra gì. Không có đường nào lặp vô hạn ở đây.
        """
        if state.get("da_truy_hoi"):
            return False
        return not state.get("tool_context") and not state.get("chunks")

    def _prompt(self, state: AgentState):
        from src.models.chat import ChatMessage, MessageRole

        return ChatMessage(
            role=MessageRole.USER,
            content=_PROMPT.format(
                query=state.get("query", ""),
                evidence=_describe_evidence(state),
                tools=_describe_tools(self._registry),
                toi_da=_TOI_DA_PHUONG_AN,
            ),
        )

    def _doc_ket_qua(self, raw: str, state: AgentState) -> dict[str, Any]:
        """Parse JSON model trả về. Hỏng kiểu gì cũng rơi về `answer`.

        Không đoán ý model: kế hoạch đọc không ra thì trả lời bằng những gì đang
        có, còn hơn gọi nhầm tool rồi báo số sai cho khách.
        """
        match = _JSON_BLOCK.search(raw or "")
        if match is None:
            logger.warning("Plan không trả JSON, rơi về answer")
            return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

        try:
            data = json.loads(match.group(0))
        except ValueError:
            logger.warning("Plan trả JSON hỏng, rơi về answer")
            return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

        action = str(data.get("action", "")).strip().lower()
        reason = str(data.get("reason", "")).strip()

        if action == CLARIFY:
            if self._phai_tra_cuu_truoc(state):
                return self._quyet(RETRIEVE, "Tra kho tài liệu trước khi hỏi lại.")
            # Tài liệu đã truy hồi là nguồn phương án ĐÁNG TIN nhất — nó liệt
            # kê đúng những gì có thật. Chỉ khi không có tài liệu nào (clarify
            # sau khi chạy tool) mới nhận đề xuất của model.
            return self._quyet(
                CLARIFY,
                reason or "Bạn cho mình thêm thông tin để tra cứu chính xác nhé.",
                options=_phuong_an_tu_tai_lieu(state) or _doc_phuong_an(data),
            )

        if action == ACT:
            tool = str(data.get("tool", "")).strip()
            if self._registry.get(tool) is None:
                logger.warning("Plan chọn tool không có trong registry: %r", tool)
                return self._quyet(ANSWER, "Trả lời bằng dữ kiện hiện có.")

            args = data.get("args")
            args = args if isinstance(args, dict) else {}

            # Đã thử đúng hành động này rồi mà vẫn quay lại xin nữa nghĩa là
            # agent kẹt: tool không có dữ liệu đó, gọi lại lần nữa cũng vậy.
            # Cắt sớm thay vì đốt nốt trần vòng lặp cho một việc vô ích.
            if _chu_ky(tool, _lam_sach(args)) in set(state.get("da_thu", [])):
                logger.info("Plan lặp lại hành động đã thử, dừng: %s", tool)
                return self._quyet(ANSWER, "Đã tra nhưng không có thêm dữ liệu.")

            return self._quyet(ACT, reason or f"Cần tra thêm bằng {tool}.", tool=tool, args=args)

        return self._quyet(ANSWER, reason or "Đã đủ dữ kiện để trả lời.")

    @staticmethod
    def _quyet(
        action: str,
        reason: str,
        *,
        tool: str = "",
        args: dict | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        quyet: dict[str, Any] = {
            "plan_action": action,
            "plan_reason": reason,
            "plan_tool": tool,
            "plan_args": args or {},
            "plan_options": options or [],
        }
        # Quyết định `retrieve` phải tự bật cờ: RetrieveNode thoát ngay khi
        # `needs_retrieval` tắt, mà ca cần chốt này nhất chính là ca router đã
        # tắt nó. Không bật thì node chạy rỗng và vòng lặp quay lại y nguyên.
        if action == RETRIEVE:
            quyet["needs_retrieval"] = True
        return quyet
