"""Test vòng lặp agent: plan quyết định, act thực thi, trần lần lặp chặn.

Trọng tâm là những ca khiến agent chạy loạn hoặc đốt quota, không phải ca đẹp:
model trả rác, model chọn tool không tồn tại, model cứ đòi gọi thêm mãi.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.contracts import AgentTool, ToolResult
from src.agents.graph import build_graph, build_nodes, route_after_plan
from src.agents.nodes.act import ActNode
from src.agents.nodes.plan import ACT, ANSWER, CLARIFY, RETRIEVE, PlanNode
from src.agents.state import Intent, initial_state
from src.agents.tools.registry import ToolBinding, ToolRegistry
from src.data.contracts import Chunk
from src.rag.retriever import EmptyRetriever


class _KichBanLLM:
    """LLM giả trả lần lượt các chuỗi đã định sẵn."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.so_lan_goi = 0

    async def complete(self, messages, **kwargs) -> str:  # noqa: ARG002
        self.so_lan_goi += 1
        return self._replies.pop(0) if self._replies else '{"action": "answer"}'

    async def stream(self, messages, **kwargs):  # noqa: ARG002
        yield "xong"


class _ToolGia(AgentTool):
    name = "tra_gia"
    description = "Tra giá căn."

    def __init__(self, *, data: Any = None, ok: bool = True) -> None:
        self._data = data if data is not None else [{"unit_code": "VOP345"}]
        self._ok = ok
        self.so_lan_chay = 0

    async def run(self, **kwargs: Any) -> ToolResult:
        self.so_lan_chay += 1
        if not self._ok:
            return ToolResult.failure("hỏng có chủ đích")
        return ToolResult(ok=True, data=self._data, source="test:db")


def _chunk(doc_title: str) -> Chunk:
    """Chunk tối giản — chỉ `doc_title` có ý nghĩa với test phương án."""
    return Chunk(id=f"{doc_title}::0", text="…", doc_id=doc_title, doc_title=doc_title)


def _registry(tool: AgentTool) -> ToolRegistry:
    reg = ToolRegistry()
    reg.add(tool, ToolBinding(intents=frozenset({Intent.LISTING}), build_args=lambda q: None))
    return reg


# ---------- Trần vòng lặp ----------


@pytest.mark.asyncio
async def test_het_tran_thi_ep_tra_loi_du_model_doi_goi_tiep():
    """Model tham lam cũng không vượt được trần — đây là chốt chặn quota."""
    llm = _KichBanLLM(*['{"action": "act", "tool": "tra_gia", "args": {}}'] * 5)
    plan = PlanNode(llm, max_iterations=2, registry=_registry(_ToolGia()))

    state = initial_state("giá căn nào rẻ nhất", "s1")
    state["iterations"] = 2

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == ANSWER
    assert llm.so_lan_goi == 0  # het tran thi khong hoi model nua


@pytest.mark.asyncio
async def test_act_tang_so_vong_ke_ca_khi_tool_hong():
    """Chỉ tăng khi thành công thì tool luôn lỗi sẽ lặp tới trần thời gian."""
    tool = _ToolGia(ok=False)
    state = initial_state("x", "s1")
    state.update({"plan_tool": "tra_gia", "plan_args": {}, "iterations": 0})

    ket_qua = await ActNode(_registry(tool))(state)

    assert ket_qua["iterations"] == 1
    assert not ket_qua.get("tool_context")


# ---------- Không tự tắt vòng lặp ----------


@pytest.mark.asyncio
async def test_da_co_du_lieu_tool_van_hoi_model_de_biet_con_thieu_gi():
    """Từng có đường tắt 'có tool_context ⇒ trả lời luôn' và nó giết vòng lặp.

    'So sánh VOP345 và VOP397': ToolsNode chỉ bắt mã đầu, đường tắt thấy đã có
    dữ liệu nên dừng — trả lời một căn rồi im. Plan phải được quyền nhìn bằng
    chứng và nói còn thiếu căn thứ hai.
    """
    llm = _KichBanLLM('{"action": "act", "tool": "tra_gia", "args": {"unit_code": "VOP397"}}')
    plan = PlanNode(llm, max_iterations=2, registry=_registry(_ToolGia()))

    state = initial_state("so sánh căn VOP345 và VOP397", "s1")
    state["tool_context"] = '{"unit_code": "VOP345"}'

    ket_qua = await plan(state)

    assert llm.so_lan_goi == 1
    assert ket_qua["plan_action"] == ACT
    assert ket_qua["plan_args"] == {"unit_code": "VOP397"}


# ---------- Luật: mã căn trong câu hỏi mà bằng chứng chưa có ----------


def _registry_tra_ma_can(tool: AgentTool | None = None) -> ToolRegistry:
    """Registry có tool ĐÚNG TÊN inventory_lookup để luật tra mã căn dùng được."""
    reg = ToolRegistry()
    t = tool or _ToolGia()
    t.name = "inventory_lookup"
    reg.add(t, _binding((Intent.LISTING,), lambda q: None))
    return reg


def _binding(intents, build_args):
    from src.agents.tools.registry import ToolBinding

    return ToolBinding(intents=frozenset(intents), build_args=build_args)


@pytest.mark.asyncio
async def test_thieu_ma_can_thi_di_lay_khong_hoi_model():
    """Ca thật đã hỏng: 'so sánh VOP217 và VOP902' — tool tất định chỉ bắt mã
    đầu, còn model tự nhận nhầm là 'đã có đủ thông tin' rồi dừng."""
    llm = _KichBanLLM('{"action": "answer", "reason": "Đã có đủ thông tin."}')
    plan = PlanNode(llm, max_iterations=3, registry=_registry_tra_ma_can())

    state = initial_state("so sánh VOP217 và VOP902", "s1")
    state["tool_context"] = '[inventory_lookup] {"unit_code": "VOP217"}'

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == ACT
    assert ket_qua["plan_args"] == {"unit_code": "VOP902"}
    assert llm.so_lan_goi == 0  # doi chieu chuoi la du, khong ton luot goi model


@pytest.mark.asyncio
async def test_co_du_moi_ma_roi_thi_moi_hoi_model():
    llm = _KichBanLLM('{"action": "answer", "reason": "Đủ rồi."}')
    plan = PlanNode(llm, max_iterations=3, registry=_registry_tra_ma_can())

    state = initial_state("so sánh VOP217 và VOP902", "s1")
    state["tool_context"] = "VOP217 ... VOP902 ..."

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == ANSWER
    assert llm.so_lan_goi == 1


@pytest.mark.asyncio
async def test_da_tra_ma_do_ma_khong_ra_thi_khong_lap_lai():
    llm = _KichBanLLM('{"action": "answer", "reason": "Không có dữ liệu căn đó."}')
    plan = PlanNode(llm, max_iterations=3, registry=_registry_tra_ma_can())

    state = initial_state("so sánh VOP217 và VOP902", "s1")
    state["tool_context"] = "VOP217"
    state["da_thu"] = ['inventory_lookup({"unit_code": "VOP902"})']

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == ANSWER


@pytest.mark.asyncio
async def test_ba_can_thi_lay_lan_luot_tung_ma():
    llm = _KichBanLLM()
    plan = PlanNode(llm, max_iterations=5, registry=_registry_tra_ma_can())

    state = initial_state("so sánh VOP217, VOP902 và VOP345", "s1")
    state["tool_context"] = "VOP217"

    ket_qua = await plan(state)
    assert ket_qua["plan_args"] == {"unit_code": "VOP902"}

    state["tool_context"] += " VOP902"
    state["da_thu"] = ['inventory_lookup({"unit_code": "VOP902"})']
    ket_qua = await plan(state)
    assert ket_qua["plan_args"] == {"unit_code": "VOP345"}


# ---------- Model trả rác ----------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    ["không phải json", "", '{"action": "act"} nhưng thiếu ngoặc {{{', '{"action": "bay_len_troi"}'],
)
async def test_model_tra_rac_thi_roi_ve_answer(raw):
    """Không đoán ý model: đọc không ra thì trả lời bằng dữ kiện đang có."""
    plan = PlanNode(_KichBanLLM(raw), max_iterations=2, registry=_registry(_ToolGia()))

    ket_qua = await plan(initial_state("x", "s1"))

    assert ket_qua["plan_action"] == ANSWER


@pytest.mark.asyncio
async def test_chon_tool_khong_ton_tai_thi_khong_chay_gi():
    llm = _KichBanLLM('{"action": "act", "tool": "tool_ma", "args": {}}')
    plan = PlanNode(llm, max_iterations=2, registry=_registry(_ToolGia()))

    ket_qua = await plan(initial_state("x", "s1"))

    assert ket_qua["plan_action"] == ANSWER


@pytest.mark.asyncio
async def test_json_boc_trong_markdown_van_doc_duoc():
    """Model hay bọc ```json dù đã dặn đừng."""
    raw = '```json\n{"action": "clarify", "reason": "Bạn muốn tìm ở toà nào?"}\n```'
    plan = PlanNode(_KichBanLLM(raw), max_iterations=2, registry=_registry(_ToolGia()))

    # Đã truy hồi rồi thì `clarify` mới được đi tiếp — nếu không, chốt "không
    # bỏ cuộc khi chưa tra cứu" sẽ đổi hướng sang `retrieve` và test này không
    # còn kiểm được việc đọc JSON nữa.
    state = initial_state("tìm căn", "s1")
    state["da_truy_hoi"] = True

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == CLARIFY
    assert "toà nào" in ket_qua["plan_reason"]


# ---------- Tham số do model sinh ----------


@pytest.mark.asyncio
async def test_bo_tham_so_rong_model_dien_thua():
    """Model điền đủ mọi trường, dùng "" cho thứ không áp dụng.

    Tool chỉ coi None là "không lọc", nên "" thành `ILIKE ''` và không khớp gì —
    tra đúng mã căn vẫn trả rỗng rồi agent lặp cho hết trần. Đã xảy ra thật.
    """
    nhan: dict[str, Any] = {}

    class _Ghi(_ToolGia):
        async def run(self, **kwargs):
            nhan.update(kwargs)
            return await super().run(**kwargs)

    tool = _Ghi()
    state = initial_state("x", "s1")
    state.update({"plan_tool": "tra_gia", "plan_args": {"unit_code": "VOP397", "building": "", "unit_type": None}})

    await ActNode(_registry(tool))(state)

    assert nhan == {"unit_code": "VOP397"}


@pytest.mark.asyncio
async def test_lap_lai_hanh_dong_da_thu_thi_dung_som():
    """Xin lại đúng thứ vừa thử nghĩa là agent kẹt — gọi nữa cũng ra kết quả cũ."""
    llm = _KichBanLLM('{"action": "act", "tool": "tra_gia", "args": {"unit_code": "VOP397"}}')
    plan = PlanNode(llm, max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("x", "s1")
    state["da_thu"] = ['tra_gia({"unit_code": "VOP397"})']

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == ANSWER
    assert "không có thêm dữ liệu" in ket_qua["plan_reason"]


@pytest.mark.asyncio
async def test_act_ghi_lai_chu_ky_hanh_dong_da_thu():
    state = initial_state("x", "s1")
    state.update({"plan_tool": "tra_gia", "plan_args": {"unit_code": "VOP397", "building": ""}})

    ket_qua = await ActNode(_registry(_ToolGia()))(state)

    assert ket_qua["da_thu"] == ['tra_gia({"unit_code": "VOP397"})']


# ---------- Điều hướng ----------


def test_route_theo_ke_hoach():
    assert route_after_plan({"plan_action": ACT}) == "act"
    assert route_after_plan({"plan_action": ANSWER}) == "generate"
    assert route_after_plan({"plan_action": CLARIFY}) == "generate"
    assert route_after_plan({"plan_action": ACT, "error": "hỏng"}) == "generate"


# ---------- Cờ bật/tắt ----------


def test_tat_co_thi_khong_co_node_vong_lap(scripted_llm, settings):
    settings.enable_agent_loop = False

    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)

    assert "plan" not in nodes and "act" not in nodes


def test_bat_co_thi_co_node_vong_lap(scripted_llm, settings):
    settings.enable_agent_loop = True

    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)

    assert "plan" in nodes and "act" in nodes


@pytest.mark.asyncio
async def test_graph_tat_co_van_chay_dung_duong_cu(scripted_llm, settings):
    settings.enable_agent_loop = False
    nodes = build_nodes(scripted_llm, EmptyRetriever(), settings)

    result = await build_graph(nodes).ainvoke(initial_state("Xin chào", "s1"))

    assert result["answer"]
    assert result.get("iterations", 0) == 0


@pytest.mark.asyncio
async def test_graph_bat_co_chay_het_vong_lap_va_dung_dung_tran(settings):
    """Model đòi gọi tool mãi — graph phải dừng ở TRẦN, không treo.

    Tham số khác nhau mỗi lượt để chốt chặn "lặp lại chính mình" không cắt
    trước: bài test này đo trần vòng lặp, không đo chốt kia.
    """
    settings.enable_agent_loop = True
    settings.agent_max_iterations = 2
    llm = _KichBanLLM(
        *[f'{{"action": "act", "tool": "tra_gia", "args": {{"unit_code": "VOP{i:03d}"}}}}' for i in range(10)]
    )

    tool = _ToolGia()
    nodes = build_nodes(llm, EmptyRetriever(), settings)
    nodes["plan"] = PlanNode(llm, max_iterations=2, registry=_registry(tool))
    nodes["act"] = ActNode(_registry(tool))

    result = await build_graph(nodes).ainvoke(initial_state("giá căn rẻ nhất", "s1"))

    assert result["iterations"] == 2
    assert tool.so_lan_chay == 2
    assert result["answer"]


@pytest.mark.asyncio
async def test_clarify_tra_ve_cau_hoi_nguoc_khong_bi_guardrail_chan(settings):
    """Guardrail không được thay câu hỏi ngược bằng thông điệp 'chưa đủ dữ liệu'."""
    settings.enable_agent_loop = True
    cau_hoi = "Bạn muốn tìm căn ở toà nào?"
    llm = _KichBanLLM(f'{{"action": "clarify", "reason": "{cau_hoi}"}}')

    nodes = build_nodes(llm, EmptyRetriever(), settings)
    nodes["plan"] = PlanNode(llm, max_iterations=2, registry=_registry(_ToolGia()))
    nodes["act"] = ActNode(_registry(_ToolGia()))

    state = initial_state("tìm căn", "s1")
    state["needs_retrieval"] = True
    result = await build_graph(nodes).ainvoke(state)

    assert result["answer"] == cau_hoi


# ---------- Chốt: không bỏ cuộc khi chưa tra cứu ----------


@pytest.mark.asyncio
async def test_doi_hoi_nguoc_khi_chua_tra_cuu_thi_bi_ep_di_truy_hoi():
    """Ca thật: "Ocean park có ưu đãi gì" bị router xếp `general`.

    Node retrieve không chạy, plan nhìn state rỗng nên chọn `clarify` — rồi bịa
    trục mơ hồ, hỏi "loại ưu đãi nào?" trong khi trục thật là Ocean Park 2 hay
    3. Truy hồi cho độ phủ 0.919 với đúng hai tài liệu đó.
    """
    raw = '{"action": "clarify", "reason": "Bạn quan tâm loại ưu đãi nào?"}'
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    ket_qua = await plan(initial_state("Ocean park có ưu đãi gì", "s1"))

    assert ket_qua["plan_action"] == RETRIEVE
    # Phải tự bật cờ, nếu không RetrieveNode thoát ngay và vòng lặp quay lại y cũ.
    assert ket_qua["needs_retrieval"] is True


@pytest.mark.asyncio
async def test_tra_cuu_xong_van_khong_ra_gi_thi_duoc_hoi_nguoc():
    """Chốt chỉ ép ĐÚNG MỘT LẦN — tra rồi mà rỗng thì hỏi lại là hợp lý.

    Nếu điều kiện chỉ nhìn `chunks` rỗng thì plan sẽ đòi truy hồi mãi.
    """
    raw = '{"action": "clarify", "reason": "Bạn muốn xem dự án nào?"}'
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("có ưu đãi gì", "s1")
    state["da_truy_hoi"] = True  # đã tìm, không thấy gì

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == CLARIFY


@pytest.mark.asyncio
async def test_co_ket_qua_tool_thi_khong_bi_ep_truy_hoi():
    """Đã có bằng chứng từ tool thì hỏi ngược là quyết định có cơ sở."""
    raw = '{"action": "clarify", "reason": "Bạn hỏi căn nào trong hai căn này?"}'
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("căn nào rẻ hơn", "s1")
    state["tool_context"] = "VOP345: 3.2 tỷ"

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == CLARIFY


# ---------- Phương án chọn sẵn kèm câu hỏi ngược ----------


@pytest.mark.asyncio
async def test_phuong_an_duoc_giu_lai_va_lam_sach():
    """Model trả lẫn rác thì lọc, không để một phần tử hỏng cả dãy nút."""
    raw = (
        '{"action": "clarify", "reason": "Bạn hỏi dự án nào?",'
        ' "options": ["Ưu đãi Ocean Park 2", null, "  ", "Ưu đãi Ocean Park 3",'
        ' "Ưu đãi Ocean Park 2", 5]}'
    )
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("Ocean park có ưu đãi gì", "s1")
    state["da_truy_hoi"] = True

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == CLARIFY
    assert ket_qua["plan_options"] == ["Ưu đãi Ocean Park 2", "Ưu đãi Ocean Park 3"]


@pytest.mark.asyncio
async def test_khong_co_phuong_an_thi_tra_mang_rong():
    """Thiếu "options" không được làm hỏng quyết định clarify."""
    plan = PlanNode(
        _KichBanLLM('{"action": "clarify", "reason": "Bạn hỏi dự án nào?"}'),
        max_iterations=3,
        registry=_registry(_ToolGia()),
    )

    state = initial_state("có ưu đãi gì", "s1")
    state["da_truy_hoi"] = True

    ket_qua = await plan(state)

    assert ket_qua["plan_options"] == []


def test_route_after_plan_dua_retrieve_ve_dung_node():
    """Graph phải biết đường đi mới, nếu không quyết định `retrieve` rơi vào generate."""
    assert route_after_plan({"plan_action": RETRIEVE}) == "retrieve"
    assert route_after_plan({"plan_action": RETRIEVE, "error": "hỏng"}) == "generate"


@pytest.mark.asyncio
async def test_phuong_an_lay_tu_ten_tai_lieu_khong_de_model_bia():
    """Ca thật: kho chỉ có ưu đãi OP2 và OP3, model vẫn chào "ưu đãi OP1".

    Người dùng bấm vào, agent tra không ra, lại hỏi ngược tiếp — hai lượt trôi
    đi mà không tiến thêm bước nào.
    """
    raw = (
        '{"action": "clarify", "reason": "Bạn muốn xem dự án nào?",'
        ' "options": ["Ưu đãi Ocean Park 1", "Ưu đãi Ocean Park 5"]}'
    )
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("Ocean park có ưu đãi gì", "s1")
    state["da_truy_hoi"] = True
    state["chunks"] = [
        _chunk("Ưu đãi của Vinhomes OceanPark 2"),
        _chunk("Ưu đãi Vinhomes OceanPark 3"),
        _chunk("Ưu đãi của Vinhomes OceanPark 2"),  # trùng, phải gộp
    ]

    ket_qua = await plan(state)

    assert ket_qua["plan_action"] == CLARIFY
    # Tên tài liệu thắng, đề xuất bịa của model bị bỏ hoàn toàn.
    assert ket_qua["plan_options"] == [
        "Ưu đãi của Vinhomes OceanPark 2",
        "Ưu đãi Vinhomes OceanPark 3",
    ]


@pytest.mark.asyncio
async def test_khong_co_tai_lieu_thi_van_dung_de_xuat_cua_model():
    """Clarify sau khi chạy tool: không có tên tài liệu nào để bám."""
    raw = '{"action": "clarify", "reason": "Căn nào?", "options": ["Căn VOP345", "Căn VOP397"]}'
    plan = PlanNode(_KichBanLLM(raw), max_iterations=3, registry=_registry(_ToolGia()))

    state = initial_state("căn nào rẻ hơn", "s1")
    state["tool_context"] = "VOP345 ... VOP397 ..."

    ket_qua = await plan(state)

    assert ket_qua["plan_options"] == ["Căn VOP345", "Căn VOP397"]
