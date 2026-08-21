"""Test từng node của agent — nhanh, không gọi mạng."""

from __future__ import annotations

import pytest

from src.agents.nodes.base import BaseNode
from src.agents.nodes.generate import GenerateNode, build_messages, merged_context
from src.agents.nodes.guardrail import INSUFFICIENT_MESSAGE, GuardrailNode
from src.agents.nodes.retrieve import RetrieveNode, _cau_de_truy_hoi
from src.agents.nodes.router import RouterNode
from src.agents.state import Intent, initial_state
from src.data.contracts import Chunk
from src.models.chat import ChatMessage, Citation, MessageRole
from src.rag.contracts import RetrievalResult
from src.services.llm import ScriptedProvider
from tests.conftest import FAKE_REPLY


class _BrokenNode(BaseNode):
    name = "broken"

    async def execute(self, state):
        raise RuntimeError("hỏng rồi")


class _StubRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    async def retrieve(self, query, *, filters=None, top_k=None, top_n=None):
        return self._result


# ---------------- BaseNode ----------------


@pytest.mark.asyncio
async def test_base_node_bat_loi_thay_vi_lam_dut_graph():
    result = await _BrokenNode()(initial_state("hỏi gì đó", "s1"))

    assert "hỏng rồi" in result["error"]


@pytest.mark.asyncio
async def test_base_node_ghi_lai_thoi_gian_chay(scripted_llm):
    result = await RouterNode(scripted_llm)(initial_state("Xin chào", "s1"))

    assert "router_ms" in result["metadata"]


# ---------------- Router ----------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Thủ tục sang tên sổ đỏ gồm những gì?", Intent.LEGAL),
        ("Giá căn hộ Cầu Giấy bao nhiêu?", Intent.PRICE),
        ("Viết tin đăng bán căn 2PN giúp mình", Intent.DRAFT),
        ("Tìm căn hộ 2PN dưới 4 tỷ", Intent.LISTING),
    ],
)
async def test_router_bat_intent_bang_tu_khoa(scripted_llm, query, expected):
    """Luật từ khoá chạy trước để khỏi tốn một lượt gọi LLM."""
    result = await RouterNode(scripted_llm)(initial_state(query, "s1"))

    assert result["intent"] == expected


@pytest.mark.asyncio
async def test_router_nhan_la_thi_roi_ve_general(scripted_llm):
    """LLM trả nhãn không hợp lệ thì router phải fallback, không được nổ."""
    result = await RouterNode(scripted_llm)(initial_state("Xin chào bạn", "s1"))

    assert result["intent"] == Intent.GENERAL
    assert result["needs_retrieval"] is False


@pytest.mark.asyncio
async def test_router_khong_co_lich_su_thi_khong_rut_thuc_the(scripted_llm):
    """Lượt đầu không có gì để giải tham chiếu — bỏ hẳn bước, giữ nguyên hành vi cũ.

    Đây là điều kiện để mọi con số eval cũ vẫn so sánh được: 20 câu trong bộ dữ
    liệu đều một lượt, nên chúng phải chạy y hệt trước khi có tính năng này.
    """
    result = await RouterNode(scripted_llm)(initial_state("Tìm căn 2PN dưới 4 tỷ", "s1"))

    assert result["entities"] == {}


@pytest.mark.asyncio
async def test_router_co_lich_su_thi_rut_thuc_the(scripted_llm):
    """Có lịch sử thì gọi model một lượt nữa để giải tham chiếu."""
    lich_su = [
        ChatMessage(role=MessageRole.USER, content="các căn dưới 4 tỷ ở Ocean Park 1"),
        ChatMessage(role=MessageRole.ASSISTANT, content="Có 20 căn phù hợp."),
    ]
    llm = ScriptedProvider('{"phan_khu": "Ocean Park 1", "gia_max": 4}', delay_s=0)

    result = await RouterNode(llm)(initial_state("liệt kê 20 căn đó", "s1", lich_su))

    assert result["entities"] == {"phan_khu": "Ocean Park 1", "gia_max": 4.0}


@pytest.mark.asyncio
async def test_router_thuc_the_hong_thi_khong_lam_dut_luot():
    """Rút thực thể là phần THÊM — hỏng thì quay về hành vi cũ, không nổ ra ngoài."""
    lich_su = [ChatMessage(role=MessageRole.ASSISTANT, content="Có 20 căn.")]
    llm = ScriptedProvider("xin lỗi tôi không hiểu", delay_s=0)

    result = await RouterNode(llm)(initial_state("liệt kê 20 căn đó", "s1", lich_su))

    assert result["entities"] == {}
    assert result["intent"] is not None


# ---------------- Retrieve ----------------


@pytest.mark.asyncio
async def test_retrieve_bo_qua_khi_khong_can_tra_cuu():
    node = RetrieveNode(_StubRetriever(RetrievalResult()))
    state = initial_state("Xin chào", "s1")
    state["needs_retrieval"] = False

    result = await node(state)

    assert result["chunks"] == []
    assert result["context"] == ""


@pytest.mark.asyncio
async def test_retrieve_sinh_citation_tu_chunk():
    chunk = Chunk(
        id="c1",
        text="Chính sách chiết khấu 5%.",
        doc_id="doc-1",
        doc_title="Chính sách bán hàng",
        version="v2",
        page=3,
    )
    node = RetrieveNode(_StubRetriever(RetrievalResult(chunks=[chunk], coverage=0.9)))
    state = initial_state("Chiết khấu bao nhiêu?", "s1")
    state["needs_retrieval"] = True

    result = await node(state)

    assert result["coverage"] == 0.9
    assert result["citations"][0].doc_id == "doc-1"
    assert result["citations"][0].version == "v2"


# ---------------- Generate ----------------


def test_build_messages_khong_co_context_thi_giu_nguyen_cau_hoi():
    messages = build_messages(initial_state("Giá thế nào?", "s1"))

    assert messages[0].role == MessageRole.SYSTEM
    assert messages[-1].content == "Giá thế nào?"


def test_build_messages_co_context_thi_ep_grounding():
    state = initial_state("Giá thế nào?", "s1")
    state["context"] = "Giá bán 3,85 tỷ."

    messages = build_messages(state)

    assert "<ngu_canh>" in messages[-1].content
    assert "Giá bán 3,85 tỷ." in messages[-1].content


@pytest.mark.asyncio
async def test_generate_tra_ve_cau_tra_loi(scripted_llm):
    result = await GenerateNode(scripted_llm)(initial_state("Xin chào", "s1"))

    assert result["answer"] == FAKE_REPLY


def test_merged_context_dat_so_lieu_tool_truoc_tai_lieu():
    """Khi tool và tài liệu nói khác nhau, cái model đọc trước phải là số liệu
    đọc thẳng từ nguồn sự thật, không phải bản chụp trong vector store."""
    state = initial_state("Giá căn VOP345?", "s1")
    state["tool_context"] = "SO_LIEU_TOOL"
    state["context"] = "TAI_LIEU"

    merged = merged_context(state)

    assert merged.index("SO_LIEU_TOOL") < merged.index("TAI_LIEU")


def test_merged_context_bo_phan_rong():
    state = initial_state("Xin chào", "s1")
    state["tool_context"] = ""
    state["context"] = "TAI_LIEU"

    assert merged_context(state) == "TAI_LIEU"


# ---------------- Guardrail ----------------


@pytest.mark.asyncio
async def test_guardrail_tu_choi_khi_do_phu_thap():
    state = initial_state("Chính sách chiết khấu?", "s1")
    state["needs_retrieval"] = True
    state["chunks"] = []
    state["coverage"] = 0.1

    result = await GuardrailNode(0.35)(state)

    assert result["answer"] == INSUFFICIENT_MESSAGE
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_guardrail_cho_qua_khi_du_do_phu():
    chunk = Chunk(id="c1", text="nội dung", doc_id="d1")
    state = initial_state("Chính sách chiết khấu?", "s1")
    state["needs_retrieval"] = True
    state["chunks"] = [chunk]
    state["coverage"] = 0.8
    state["answer"] = "Chiết khấu 5%."

    result = await GuardrailNode(0.35)(state)

    assert "answer" not in result


@pytest.mark.asyncio
async def test_guardrail_gan_co_nhay_cam_khi_co_gia_kem_cam_ket():
    state = initial_state("Soạn tin gửi khách", "s1")
    state["answer"] = "Căn này 3,85 tỷ, bên em cam kết giữ chỗ cho anh."

    result = await GuardrailNode(0.35)(state)

    assert result["is_sensitive"] is True


@pytest.mark.asyncio
async def test_guardrail_khong_gan_co_khi_chi_co_gia():
    state = initial_state("Giá bao nhiêu", "s1")
    state["answer"] = "Mặt bằng giá khu vực khoảng 56 tr/m²."

    result = await GuardrailNode(0.35)(state)

    assert result["is_sensitive"] is False


@pytest.mark.asyncio
async def test_guardrail_khong_tu_choi_khi_tool_da_co_so_lieu():
    """Hỏi giá một căn cụ thể: nhãn bật needs_retrieval nhưng kho tài liệu
    không chứa giá từng căn, nên độ phủ luôn 0. Tool đã cầm số đúng thì không
    được từ chối."""
    state = initial_state("Giá căn VOP345?", "s1")
    state["needs_retrieval"] = True
    state["chunks"] = []
    state["coverage"] = 0.0
    state["tool_context"] = '[inventory_lookup] ...\n{"unit_code": "VOP345"}'
    state["answer"] = "Căn VOP345 giá 2,7 tỷ, còn trống."

    result = await GuardrailNode(0.35)(state)

    assert "answer" not in result


@pytest.mark.asyncio
async def test_guardrail_gop_nguon_tai_lieu_va_nguon_tool():
    state = initial_state("Giá căn VOP345?", "s1")
    state["citations"] = [Citation(doc_id="d1", title="Bảng giá", kind="doc")]
    state["tool_citations"] = [Citation(doc_id="inventory:postgres", title="VOP345", kind="db")]
    state["answer"] = "Căn VOP345 giá 2,7 tỷ theo Bảng giá."

    result = await GuardrailNode(0.35)(state)

    assert [c.kind for c in result["citations"]] == ["doc", "db"]


@pytest.mark.asyncio
async def test_guardrail_bo_nguon_cau_tra_loi_khong_dung():
    """Truy hồi trả về mọi chunk nó tìm thấy, không phải mọi chunk model dùng.

    Ca thật: hỏi căn ở Ocean Park 1, trả lời ba căn OP1, mà dòng nguồn liệt kê
    cả tổng quan OP2, OP3 và ưu đãi OP2 — vector search có trả về nhưng model
    không hề dùng.
    """
    state = initial_state("Căn ở Ocean Park 1?", "s1")
    state["tool_context"] = '[inventory_search] {"can_hien_thi": [{"unit_code": "VOP758"}]}'
    state["citations"] = [
        Citation(doc_id="d1", title="Tổng quan dự án Vinhomes Ocean Park 2", kind="doc"),
        Citation(doc_id="d2", title="Ưu đãi của Vinhomes OceanPark 2", kind="doc"),
    ]
    state["tool_citations"] = [
        Citation(doc_id="inventory:postgres", title="VOP758", kind="db"),
        Citation(doc_id="inventory:postgres", title="VOP893", kind="db"),
    ]
    state["answer"] = "Căn VOP758 giá 2,750 tỷ, 1PN, hướng Đông Nam."

    result = await GuardrailNode(0.35)(state)

    assert [c.title for c in result["citations"]] == ["VOP758"]


@pytest.mark.asyncio
async def test_guardrail_khong_xoa_sach_nguon_khi_tra_loi_khong_nhac_ma_can():
    """Không nhắc lại mã căn không có nghĩa là số liệu tự nhiên mà có."""
    state = initial_state("Căn VOP345 giá bao nhiêu?", "s1")
    state["tool_context"] = '[inventory_lookup] {"unit_code": "VOP345"}'
    state["tool_citations"] = [Citation(doc_id="inventory:postgres", title="VOP345", kind="db")]
    state["answer"] = "Căn này giá 2,7 tỷ và vẫn còn trống."

    result = await GuardrailNode(0.35)(state)

    assert [c.title for c in result["citations"]] == ["VOP345"]


# ---------------- Retrieve: chọn lọc theo doc_kind ----------------


class _GhiFilter:
    """Retriever ghi lại filter được truyền vào — thứ duy nhất test này quan tâm."""

    def __init__(self) -> None:
        self.filters = None

    async def retrieve(self, query, *, filters=None, top_k=None, top_n=None):
        self.filters = filters
        return RetrievalResult()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent", "tool_context", "mong_doi"),
    [
        (Intent.DOCUMENT, "", "policy"),
        (Intent.LEGAL, "", "policy"),
        # Ca hỏng thật: "tôi có 1 tỷ, mua VOP397 thì vay thế nào" bị xếp `price`,
        # cả 5 đoạn truy hồi được đều là tin rao, chính sách lãi suất không bao
        # giờ tới tay model — rồi model tự bịa "ngân hàng cho vay 70-80%".
        (Intent.PRICE, '[inventory_lookup] {"unit_code": "VOP397"}', "policy"),
        # Chưa có dữ liệu tool thì tin rao vẫn là câu trả lời đúng.
        (Intent.PRICE, "", None),
        (Intent.LISTING, "", None),
    ],
)
async def test_loc_chinh_sach_khi_tool_da_co_du_lieu(intent, tool_context, mong_doi):
    retriever = _GhiFilter()
    state = initial_state("hỏi gì đó", "s1")
    state.update({"needs_retrieval": True, "intent": intent, "tool_context": tool_context})

    await RetrieveNode(retriever)(state)

    assert retriever.filters.doc_kind == mong_doi


@pytest.mark.asyncio
async def test_retrieve_danh_dau_da_tra_cuu():
    """`chunks` rỗng vừa có nghĩa "tìm không thấy" vừa có nghĩa "chưa tìm" —
    plan cần phân biệt hai ca đó để không hỏi ngược khi chưa tra cứu lần nào."""
    state = initial_state("hỏi gì đó", "s1")
    state["needs_retrieval"] = True

    result = await RetrieveNode(_StubRetriever(RetrievalResult()))(state)

    assert result["da_truy_hoi"] is True


# ---------------- Retrieve: làm sạch câu trước khi nhúng ----------------


def test_bo_duoi_ngu_canh_widget_truoc_khi_truy_hoi():
    """Đuôi "(căn đang xem: X)" do FE chèn làm lệch vector truy hồi.

    Ca thật: cùng câu "Chính sách hỗ trợ lãi suất chung của Vinhomes" hỏi hai
    lần ra hai kết quả khác hẳn — một lần trả lời đủ, một lần từ chối. Khác nhau
    đúng ở chỗ lượt kia đang mở một căn nên câu bị gắn thêm đuôi. Kho tài liệu
    chỉ có văn bản chính sách, không văn bản nào chứa mã căn.
    """
    assert _cau_de_truy_hoi("Chính sách lãi suất (căn đang xem: VOP437)") == "Chính sách lãi suất"
    assert _cau_de_truy_hoi("Chính sách lãi suất") == "Chính sách lãi suất"


def test_cau_chi_con_duoi_thi_giu_nguyen_ban_goc():
    """Thà nhúng hơi lệch còn hơn nhúng chuỗi rỗng."""
    goc = "(căn đang xem: VOP437)"
    assert _cau_de_truy_hoi(goc) == goc


@pytest.mark.asyncio
async def test_retrieve_truyen_cau_da_lam_sach_xuong_retriever():
    """Chốt chặn thật: retriever phải nhận câu sạch, không phải câu gốc."""
    nhan = {}

    class _GhiCau:
        async def retrieve(self, query, filters=None):
            nhan["query"] = query
            return RetrievalResult(chunks=[], coverage=0.0)

    state = initial_state("Ưu đãi Ocean Park 2 (căn đang xem: VOP437)", "s1")
    state["needs_retrieval"] = True
    state["intent"] = Intent.DOCUMENT

    await RetrieveNode(_GhiCau())(state)

    assert nhan["query"] == "Ưu đãi Ocean Park 2"
