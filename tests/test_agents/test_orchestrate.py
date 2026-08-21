"""Test cổng leo thang và vòng lặp orchestrator.

Không gọi Anthropic thật — dùng `ScriptedToolCallingProvider`. Bốn nhóm:

1. Cổng: luật nào khớp, và mặc định chỉ R1 được bật.
2. Vòng lặp: bốn chốt chặn còn nguyên.
3. An toàn: hỏng nhà cung cấp không được làm câm trợ lý.
4. Dựng graph: bật/tắt cờ ra đúng hình dạng.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.contracts import AgentTool, LLMTurn, ToolCall, ToolResult
from src.agents.graph import build_graph, build_nodes
from src.agents.leo_thang import nen_leo_thang
from src.agents.nodes.orchestrate import OrchestratorNode
from src.agents.state import initial_state
from src.agents.tools.registry import ToolRegistry
from src.core.config import Settings
from src.services.llm import ScriptedToolCallingProvider


class _ToolGia(AgentTool):
    name = "inventory_search"
    description = "Tìm căn theo tiêu chí. Trả dữ liệu thật."

    def __init__(self, data: Any = None) -> None:
        self.da_goi: list[dict[str, Any]] = []
        self._data = data if data is not None else {"can_hien_thi": [{"unit_code": "VOP397"}]}

    async def run(self, **kwargs: Any) -> ToolResult:
        self.da_goi.append(kwargs)
        return ToolResult(ok=True, data=self._data, source="inventory:postgres")


class _RetrieverGia:
    """Retriever rỗng — phần dựng graph không quan tâm truy hồi trả về gì."""

    async def retrieve(self, query: str, **kwargs: Any) -> Any:
        from src.rag.contracts import RetrievalResult

        return RetrievalResult(query=query)


def _registry(tool: AgentTool) -> ToolRegistry:
    reg = ToolRegistry()
    reg.add(tool)
    return reg


def _state(**them: Any) -> Any:
    state = initial_state("tìm căn 2PN dưới 4 tỷ", "s1")
    state.update(them)
    return state


def _goi(ten: str = "inventory_search", **args: Any) -> LLMTurn:
    return LLMTurn(tool_calls=[ToolCall(id=f"c{len(args)}", name=ten, arguments=args)])


# ---------------- 1. Cổng ----------------


class TestCongLeoThang:
    def test_r1_khop_khi_can_tra_cuu_ma_khong_gom_duoc_gi(self) -> None:
        """Đúng nhánh hôm nay trả "chưa đủ dữ liệu"."""
        assert nen_leo_thang(_state(needs_retrieval=True)) == "R1"

    def test_r1_khop_khi_co_tai_lieu_nhung_do_phu_thap(self) -> None:
        """Chốt chặn hồi quy cho một lỗi đo được trên máy thật.

        Bản đầu của R1 viết là "chunks rỗng", và nó gần như KHÔNG BAO GIỜ khớp:
        truy hồi luôn trả top-N theo độ tương đồng bất kể có liên quan không.
        Thứ quyết định từ chối là ĐỘ PHỦ, nên cổng phải đọc đúng thứ đó.
        """
        state = _state(needs_retrieval=True, chunks=[object()], coverage=0.1)

        assert nen_leo_thang(state, nguong_do_phu=0.35) == "R1"

    def test_r1_khong_khop_khi_do_phu_dat_nguong(self) -> None:
        state = _state(needs_retrieval=True, chunks=[object()], coverage=0.9)

        assert nen_leo_thang(state, nguong_do_phu=0.35) == ""

    def test_r1_khong_khop_khi_da_co_ket_qua_tool(self) -> None:
        assert nen_leo_thang(_state(needs_retrieval=True, tool_context="[x] Kết quả")) == ""

    def test_r1_khong_khop_khi_khong_can_tra_cuu(self) -> None:
        """Câu xã giao không được kéo theo một lượt gọi model đắt tiền."""
        assert nen_leo_thang(_state(needs_retrieval=False)) == ""

    def test_r2_can_ca_hai_mien_moi_khop(self) -> None:
        chi_can_ho = _state(tool_context="x", entities={"phan_khu": "Ocean Park 1"})
        du_hai_mien = _state(tool_context="x", entities={"phan_khu": "Ocean Park 1", "von_tu_co": 1.0})

        assert nen_leo_thang(chi_can_ho, bat_r2=True) == ""
        assert nen_leo_thang(du_hai_mien, bat_r2=True) == "R2"

    def test_r3_khop_khi_nhieu_ma_can_ma_so_sanh_khong_chay(self) -> None:
        state = _state(tool_context="x", entities={"ma_can": ["VOP345", "VOP397"]})

        assert nen_leo_thang(state, bat_r3=True) == "R3"

    def test_r3_khong_khop_khi_so_sanh_da_chay(self) -> None:
        """So sánh thuần đã có tool riêng lo, không cần orchestrator."""
        state = _state(
            tool_context="x",
            entities={"ma_can": ["VOP345", "VOP397"]},
            tools_ran=["so_sanh_can"],
        )

        assert nen_leo_thang(state, bat_r3=True) == ""

    def test_mac_dinh_chi_bat_r1(self) -> None:
        """R2/R3 phải bật tường minh — mỗi luật một cờ để tắt riêng được."""
        state = _state(tool_context="x", entities={"phan_khu": "OP1", "von_tu_co": 1.0})

        assert nen_leo_thang(state) == ""


# ---------------- 2. Bốn chốt chặn ----------------


class TestBonChotChan:
    @pytest.mark.asyncio
    async def test_chot1_khong_bao_gio_vuot_tran_vong_lap(self) -> None:
        """Model đòi gọi tool mãi thì phải bị cắt, không đốt hết quota."""
        tool = _ToolGia()
        provider = ScriptedToolCallingProvider([_goi(q=str(i)) for i in range(20)])
        node = OrchestratorNode(provider, registry=_registry(tool), max_iterations=2)

        await node(_state(needs_retrieval=True))

        assert len(provider.da_goi) == 2

    @pytest.mark.asyncio
    async def test_chot2_tool_bia_ten_thi_bao_loi_chu_khong_no(self) -> None:
        provider = ScriptedToolCallingProvider([_goi("tool_khong_ton_tai"), LLMTurn(text="xong")])
        node = OrchestratorNode(provider, registry=_registry(_ToolGia()))

        ket_qua = await node(_state(needs_retrieval=True))

        assert "orchestrator_loi" not in ket_qua

    @pytest.mark.asyncio
    async def test_chot3_khong_chay_lai_hanh_dong_y_het(self) -> None:
        """Agent kẹt xin đi xin lại một thứ — chạy lại chỉ tốn tiền."""
        tool = _ToolGia()
        provider = ScriptedToolCallingProvider([_goi(q="x"), _goi(q="x"), LLMTurn(text="xong")])
        node = OrchestratorNode(provider, registry=_registry(tool))

        await node(_state(needs_retrieval=True))

        assert len(tool.da_goi) == 1

    @pytest.mark.asyncio
    async def test_chot4_bo_tham_so_rong(self) -> None:
        """`building=""` thành `ILIKE ''` và không khớp gì — tra đúng mã vẫn trả rỗng."""
        tool = _ToolGia()
        provider = ScriptedToolCallingProvider([_goi(unit_code="VOP397", building=""), LLMTurn(text="xong")])
        node = OrchestratorNode(provider, registry=_registry(tool))

        await node(_state(needs_retrieval=True))

        assert tool.da_goi == [{"unit_code": "VOP397"}]


# ---------------- 3. An toàn ----------------


class TestKhongLamCamTroLy:
    @pytest.mark.asyncio
    async def test_khong_khop_luat_thi_khong_goi_model(self) -> None:
        provider = ScriptedToolCallingProvider()
        node = OrchestratorNode(provider, registry=_registry(_ToolGia()))

        ket_qua = await node(_state(needs_retrieval=True, tool_context="đã có"))

        assert ket_qua["leo_thang"] == ""
        assert provider.da_goi == []

    @pytest.mark.asyncio
    async def test_nha_cung_cap_no_thi_nuot_loi_va_di_tiep(self) -> None:
        class _No:
            async def run_turn(self, *a: Any, **k: Any) -> LLMTurn:
                raise RuntimeError("Anthropic 500")

        node = OrchestratorNode(_No(), registry=_registry(_ToolGia()))

        ket_qua = await node(_state(needs_retrieval=True))

        assert "Anthropic 500" in ket_qua["orchestrator_loi"]
        assert "error" not in ket_qua

    @pytest.mark.asyncio
    async def test_tool_no_thi_bao_lai_cho_model_chu_khong_dung_vong(self) -> None:
        class _ToolNo(_ToolGia):
            async def run(self, **kwargs: Any) -> ToolResult:
                raise RuntimeError("mất kết nối DB")

        provider = ScriptedToolCallingProvider([_goi(q="x"), LLMTurn(text="xong")])
        node = OrchestratorNode(provider, registry=_registry(_ToolNo()))

        ket_qua = await node(_state(needs_retrieval=True))

        assert "orchestrator_loi" not in ket_qua

    @pytest.mark.asyncio
    async def test_giu_lai_bang_chung_duong_tat_dinh_da_gom(self) -> None:
        """Vứt đi là bắt model tra lại từ đầu, tốn thêm một vòng.

        Dùng R3 để leo thang: R1 theo định nghĩa chỉ khớp khi CHƯA gom được gì,
        nên không dựng được tình huống "đã có bằng chứng mà vẫn leo thang".
        """
        provider = ScriptedToolCallingProvider([LLMTurn(text="đủ rồi")])
        node = OrchestratorNode(provider, registry=_registry(_ToolGia()), bat_r3=True)
        state = _state(tool_context="[cũ] Kết quả", entities={"ma_can": ["VOP345", "VOP397"]})

        ket_qua = await node(state)

        assert ket_qua["leo_thang"] == "R3"
        assert "[cũ]" in ket_qua["tool_context"]

    @pytest.mark.asyncio
    async def test_ghi_token_de_chan_ngan_sach(self) -> None:
        provider = ScriptedToolCallingProvider([LLMTurn(text="xong", token_vao=1200, token_ra=300)])
        node = OrchestratorNode(provider, registry=_registry(_ToolGia()))

        ket_qua = await node(_state(needs_retrieval=True))

        assert (ket_qua["orchestrator_token_vao"], ket_qua["orchestrator_token_ra"]) == (1200, 300)


# ---------------- 4. Dựng graph ----------------


class TestDungGraph:
    def _settings(self, **them: Any) -> Settings:
        return Settings(app_env="test", openai_api_key="test-key", **them)

    def test_tat_co_thi_khong_co_node_orchestrate(self, scripted_llm) -> None:
        nodes = build_nodes(scripted_llm, _RetrieverGia(), self._settings(enable_orchestrator=False))

        assert "orchestrate" not in nodes
        assert build_graph(nodes) is not None

    def test_bat_co_thi_co_node_va_graph_van_compile(self, scripted_llm) -> None:
        nodes = build_nodes(
            scripted_llm,
            _RetrieverGia(),
            self._settings(enable_orchestrator=True),
            ScriptedToolCallingProvider(),
        )

        assert "orchestrate" in nodes
        assert build_graph(nodes) is not None

    def test_thieu_tool_provider_thi_khong_dung_node(self, scripted_llm) -> None:
        """Bật cờ mà không cắm được provider thì phải im lặng tắt, không nổ."""
        nodes = build_nodes(scripted_llm, _RetrieverGia(), self._settings(enable_orchestrator=True))

        assert "orchestrate" not in nodes
