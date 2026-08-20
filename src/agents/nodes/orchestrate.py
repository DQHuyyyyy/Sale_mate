"""Node orchestrator — vòng lặp tool calling GỐC, chạy ở nhánh leo thang.

Khác `PlanNode` cũ ở chỗ nào: `PlanNode` bảo model viết ra một quyết định bằng
CHỮ rồi mình parse chuỗi đó. Ở đây model phát ra `tool_use` đúng chuẩn API, nên
bỏ được cả tầng parse lẫn cả một lớp lỗi ("model trả nhãn lạ"). Ràng buộc tên
tool cũng do API lo — nó chỉ chọn được trong danh sách mình đưa.

Không dựng agent thứ hai: node này dùng CHÍNH `registry` mà `ToolsNode` dùng, và
ghi ra CHÍNH các khoá state mà `generate` và `nguon.py` đang đọc
(`tool_context`, `tool_citations`, `tools_ran`). Nhờ vậy phần trích nguồn, lọc
nguồn đã dùng, gợi ý câu tiếp theo đều chạy tiếp không phải sửa gì.

Bốn chốt chặn của vòng lặp cũ vẫn còn nguyên giá trị và được giữ lại:

1. Trần vòng lặp — model đòi gọi tool mãi.
2. Tool phải có trong registry — API đã ràng, nhưng kiểm lần nữa vì spec có thể
   lệch registry sau một lần refactor.
3. Không lặp lại hành động đã thử — agent kẹt, xin đi xin lại một thứ.
4. Làm sạch tham số rỗng — model điền "" cho trường không dùng, tool dịch thành
   `ILIKE ''` rồi không khớp gì.

Node KHÔNG BAO GIỜ raise. Lỗi nhà cung cấp, hết quota, mạng đứt — tất cả đều
nuốt và đi tiếp sang `generate` với bằng chứng đã gom được. Một tính năng phụ
không được làm câm cả trợ lý.
"""

from __future__ import annotations

from typing import Any

from src.agents.contracts import (
    AgentTool,
    LLMTurn,
    OrchestratorMessage,
    ToolCall,
    ToolCallingProvider,
    ToolCallOutput,
)
from src.agents.leo_thang import nen_leo_thang
from src.agents.nodes.act import _chu_ky, _format, _lam_sach
from src.agents.nodes.base import BaseNode
from src.agents.nodes.tools import _nguon_cua_tool
from src.agents.state import AgentState
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.registry import registry as default_registry
from src.core.chi_phi import so_chi_tieu
from src.core.logging import get_logger

logger = get_logger(__name__)

_SYSTEM = """Bạn là tầng lập kế hoạch của một trợ lý bán căn hộ Ocean Park.

Nhiệm vụ: gọi tool để gom đủ dữ kiện trả lời câu hỏi, rồi dừng. Bạn KHÔNG viết
câu trả lời cuối cho khách — một bước sau sẽ lo việc đó.

Luật:
- Số liệu về căn (giá, diện tích, tình trạng, hướng) CHỈ được lấy từ tool tồn kho.
- Chính sách, ưu đãi, tiện ích lấy từ tài liệu đã truy hồi sẵn trong ngữ cảnh.
- Mọi phép tính tài chính phải qua tool tính toán, không tự nhẩm.
- Gọi ít tool nhất đủ để giải quyết. Đừng gọi lại tool với tham số y hệt.
- Thiếu dữ kiện mà không tool nào lấy được thì dừng và nói rõ thiếu gì.
- Không bịa mã căn, không bịa con số.

Dữ kiện đã gom được ở bước trước sẽ nằm trong tin nhắn của người dùng. Đọc kỹ
phần đó trước khi gọi thêm tool — gọi lại thứ đã có là tiêu tiền vô ích."""

# ⚠️ `_SYSTEM` phải là HẰNG SỐ, không được nhét dữ liệu của lượt hỏi vào.
#
# Thứ tự dựng prompt là tools → system → messages, và mốc cache đặt ở khối
# system cuối nên nó cache CẢ spec tool (~8.400 token) lẫn system. Prefix chỉ
# được tái dùng khi giống nhau TỪNG BYTE.
#
# Bản đầu format `{da_co}` (kết quả tool đã gom) vào chính system prompt. Đo
# thật: mỗi lượt đều GHI cache mới và `đọc cache 0` — trả 1,25× giá vào cho
# ~7.600 token bất biến, mọi lượt, mà không lần nào dùng lại. $0.0153/lượt thay
# vì ~$0.003.
#
# Nên phần thay đổi theo lượt đi vào MESSAGES, sau mốc cache.


class OrchestratorNode(BaseNode):
    """Vòng lặp: model chọn tool → chạy tool → model xem kết quả → lặp hoặc dừng."""

    name = "orchestrate"

    def __init__(
        self,
        provider: ToolCallingProvider,
        *,
        registry: ToolRegistry | None = None,
        max_iterations: int = 3,
        model: str | None = None,
        che_do: str = "khi_thieu",
        bat_r1: bool = True,
        bat_r2: bool = False,
        bat_r3: bool = False,
        ngan_sach_ngay_usd: float = 0.0,
        nguong_do_phu: float = 0.35,
    ) -> None:
        self._provider = provider
        self._registry = registry or default_registry
        self._max_iterations = max_iterations
        self._model = model
        self._co = {
            "che_do": che_do,
            "bat_r1": bat_r1,
            "bat_r2": bat_r2,
            "bat_r3": bat_r3,
            "nguong_do_phu": nguong_do_phu,
        }
        self._ngan_sach = ngan_sach_ngay_usd

    async def execute(self, state: AgentState) -> dict[str, Any]:
        """Gác cổng, kiểm ngân sách, rồi mới chạy.

        Cổng nằm TRONG node chứ không phải ở cạnh điều kiện của graph: để ngoài
        thì `build_graph` phải nhận `Settings` chỉ để đọc ba cờ, và đường stream
        lại phải chép lại cùng logic — đúng kiểu trôi lệch mà `CONTEXT_NODES`
        sinh ra để tránh.
        """
        luat = nen_leo_thang(state, **self._co)
        if not luat:
            return {"leo_thang": ""}

        # Hết ngân sách thì rơi về đường tất định, KHÔNG báo lỗi cho khách:
        # họ vẫn nhận được câu trả lời, chỉ là không có phần xử lý nhiều bước.
        if not so_chi_tieu.con_ngan_sach(self._ngan_sach):
            return {"leo_thang": "", "orchestrator_loi": "hết ngân sách ngày"}

        try:
            ket_qua = await self._chay_vong(state)
        except Exception as exc:  # noqa: BLE001 - biên ngoài cùng, xem docstring đầu file
            logger.warning("Orchestrator hỏng, đi tiếp bằng bằng chứng đã có: %s", exc)
            return {"leo_thang": luat, "orchestrator_loi": str(exc)}

        so_chi_tieu.ghi_nhan(
            self._model or "claude-sonnet-5",
            token_vao=ket_qua.get("orchestrator_token_vao", 0),
            token_ra=ket_qua.get("orchestrator_token_ra", 0),
            token_cache=ket_qua.get("orchestrator_token_cache", 0),
            token_ghi_cache=ket_qua.get("orchestrator_token_ghi_cache", 0),
        )
        return {"leo_thang": luat, **ket_qua}

    def tom_tat(self, result: dict[str, Any]) -> str:
        luat = result.get("leo_thang")
        if not luat:
            return "không leo thang (đường tất định đã đủ bằng chứng)"
        if result.get("orchestrator_loi"):
            return f"leo thang {luat} nhưng HỎNG: {result['orchestrator_loi']} — đi tiếp bằng bằng chứng đã có"
        return (
            f"leo thang {luat} · {self._model} · tool: {', '.join(result.get('tools_ran') or []) or 'không gọi'}"
            f" · token {result.get('orchestrator_token_vao', 0)}→{result.get('orchestrator_token_ra', 0)}"
            f" · cache đọc {result.get('orchestrator_token_cache', 0)}"
            f" / ghi {result.get('orchestrator_token_ghi_cache', 0)}"
        )

    async def _chay_vong(self, state: AgentState) -> dict[str, Any]:
        gom = _BangChung(state)
        # Dữ kiện đã gom đi vào MESSAGE, không vào system — xem chú thích ở
        # `_SYSTEM` về việc nó phá prompt cache.
        da_co = _tom_tat_da_co(state)
        loi_nhac = f"Dữ kiện đã có:\n{da_co}\n\n" if da_co else ""
        cau_hoi = state.get("query", "")
        lich_su = [OrchestratorMessage(role="user", content=f"{loi_nhac}Câu hỏi: {cau_hoi}")]
        specs = self._registry.specs()

        for vong in range(1, self._max_iterations + 1):
            luot = await self._provider.run_turn(_SYSTEM, lich_su, tools=specs, model=self._model)
            gom.cong_token(luot)

            if not luot.con_goi_tool:
                logger.info("Orchestrator dừng sau %s vòng", vong)
                break

            lich_su.append(OrchestratorMessage(role="assistant", content=luot.text, tool_calls=luot.tool_calls))
            ket_qua = [await self._chay_mot_tool(goi, gom) for goi in luot.tool_calls]
            lich_su.append(OrchestratorMessage(role="tool", tool_outputs=ket_qua))
        else:
            logger.info("Orchestrator chạm trần %s vòng", self._max_iterations)

        return gom.ket_qua()

    async def _chay_mot_tool(self, goi: ToolCall, gom: _BangChung) -> ToolCallOutput:
        """Chạy một tool model đã chọn. Mọi nhánh hỏng đều trả kết quả có chữ.

        Trả `is_error` kèm lý do thay vì im lặng: model cần biết vì sao hỏng để
        đổi cách, còn im lặng thì nó gọi lại y hệt cho tới hết trần.
        """
        tool = self._registry.get(goi.name)
        if tool is None:
            # Chốt 2. API chỉ cho chọn trong danh sách mình đưa, nhưng specs và
            # registry có thể lệch nhau sau một lần refactor.
            return ToolCallOutput(call_id=goi.id, content=f"Không có tool {goi.name}.", is_error=True)

        args = _lam_sach(goi.arguments)  # Chốt 4
        chu_ky = _chu_ky(goi.name, args)
        if chu_ky in gom.da_thu:  # Chốt 3
            return ToolCallOutput(
                call_id=goi.id,
                content="Đã gọi tool này với đúng tham số đó rồi. Đổi cách hoặc dừng lại.",
                is_error=True,
            )
        gom.da_thu.append(chu_ky)

        logger.info("Orchestrator gọi tool %s", goi.name)
        gom.tools_ran.append(goi.name)
        try:
            result = await tool.run(**args)
        except Exception as exc:  # noqa: BLE001 - tool lẻ hỏng không được dừng cả vòng
            logger.warning("Tool %s nổ: %s", goi.name, exc)
            return ToolCallOutput(call_id=goi.id, content=f"Tool lỗi: {exc}", is_error=True)

        if not result.ok:
            return ToolCallOutput(call_id=goi.id, content=result.error, is_error=True)
        if not result.data:
            return ToolCallOutput(call_id=goi.id, content="Không có dữ liệu khớp.")

        gom.them(tool, result)
        return ToolCallOutput(call_id=goi.id, content=_format(tool, result))


class _BangChung:
    """Gom bằng chứng CỘNG DỒN lên trên thứ `ToolsNode` đã lấy được.

    Cộng dồn chứ không ghi đè: đường tất định có thể đã tra được vài thứ trước
    khi cổng leo thang bật, và vứt đi là bắt model tra lại từ đầu.
    """

    def __init__(self, state: AgentState) -> None:
        self._context = state.get("tool_context", "")
        self._citations = list(state.get("tool_citations") or [])
        self.tools_ran = list(state.get("tools_ran") or [])
        # Gộp cả tool mà regex đã chạy: chốt chống lặp phải phủ cả hai đường
        # vào, không riêng vòng lặp của orchestrator.
        self.da_thu = [*(state.get("da_thu") or []), *_da_thu_tu_tools_node(state)]
        self.token_vao = 0
        self.token_ra = 0
        self.token_cache = 0
        self.token_ghi_cache = 0

    def cong_token(self, luot: LLMTurn) -> None:
        self.token_vao += luot.token_vao
        self.token_ra += luot.token_ra
        self.token_cache += luot.token_doc_cache
        self.token_ghi_cache += luot.token_ghi_cache

    def them(self, tool: AgentTool, result: Any) -> None:
        moi = _format(tool, result)
        self._context = f"{self._context}\n\n{moi}" if self._context else moi
        # Dùng lại `_nguon_cua_tool` của ToolsNode, KHÔNG tự dựng Citation.
        #
        # Bản đầu chép cách làm đơn giản của `ActNode` (lấy câu đầu trong
        # description làm nhãn) và nó tái tạo đúng một lỗi dự án đã sửa: dòng
        # "Nguồn" hiện "Tính số tiền cần vay khi mua một căn cụ thể…" thay vì
        # "VOP397". Nhãn nguồn phải là thứ người đọc kiểm chứng được — bấm vào
        # mã căn thì mở đúng căn đó, còn bấm vào mô tả tool thì không ra gì.
        #
        # Hai đường vào (regex và orchestrator) phải sinh nguồn GIỐNG NHAU, nếu
        # không thì cùng một câu hỏi cho ra hai kiểu trích nguồn tuỳ vào việc
        # cổng leo thang có mở hay không.
        self._citations.extend(_nguon_cua_tool(tool, result))

    def ket_qua(self) -> dict[str, Any]:
        # Không trả khoá "metadata": BaseNode dùng nó để gắn thời gian chạy.
        return {
            "tool_context": self._context,
            "tool_citations": self._citations,
            "tools_ran": self.tools_ran,
            "da_thu": self.da_thu,
            "orchestrator_token_vao": self.token_vao,
            "orchestrator_token_ra": self.token_ra,
            "orchestrator_token_cache": self.token_cache,
            "orchestrator_token_ghi_cache": self.token_ghi_cache,
        }


def _da_thu_tu_tools_node(state: AgentState) -> list[str]:
    """Chữ ký các tool mà `ToolsNode` (regex) ĐÃ chạy trong chính lượt này.

    Nạp vào `da_thu` để chốt chống lặp phủ luôn cả tool chạy bằng regex, không
    chỉ tool chạy trong vòng lặp. Đo trên máy thật: câu "tìm căn 2PN dưới 4 tỷ"
    thì regex chạy `inventory_search`, rồi Sonnet gọi lại y hệt — nhân đôi truy
    vấn DB và nhân đôi khối kết quả nhồi vào prompt của `generate`.

    Chỉ chặn được khi tham số TRÙNG KHỚP hoàn toàn. Model đặt tiêu chí khác đi
    thì vẫn chạy — đúng như mong muốn, vì đó là truy vấn mới thật sự.
    """
    return [_chu_ky(ten, _lam_sach(args)) for ten, args in (state.get("tool_filters") or {}).items()]


def _tom_tat_da_co(state: AgentState) -> str:
    """Nói cho model biết bước trước đã lấy được gì, để nó khỏi tra lại."""
    phan = []
    da_chay = state.get("tool_filters") or {}
    if da_chay:
        # Nêu TÊN TOOL và TIÊU CHÍ, không chỉ đưa kết quả: model nhìn kết quả
        # trần thì không biết nó đến từ tool nào và đã lọc theo gì, nên hay gọi
        # lại chính tool đó để "chắc ăn".
        phan.append(
            "Tool đã chạy (ĐỪNG gọi lại với cùng tiêu chí): "
            + " · ".join(f"{ten}({args})" for ten, args in da_chay.items())
        )
    if state.get("tool_context"):
        phan.append(f"Kết quả tool đã có:\n{state['tool_context']}")
    if state.get("chunks"):
        ten = [(c.doc_title or "").strip() for c in state["chunks"]]
        phan.append("Tài liệu đã truy hồi: " + ", ".join(t for t in dict.fromkeys(ten) if t))
    return "\n\n".join(phan)
