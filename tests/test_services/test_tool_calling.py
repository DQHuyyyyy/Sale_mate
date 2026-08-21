"""Test tầng tool calling của hai nhà cung cấp.

KHÔNG gọi API thật — client được thay bằng đồ giả. Thứ đáng test ở đây là phần
DỊCH giữa transcript nội bộ và định dạng riêng của từng SDK: OpenAI đặt kết quả
tool ở vai "tool" riêng, Claude gộp vào vai "user". Dịch sai thì model nhận
hội thoại méo và gọi lại đúng tool vừa chạy.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.agents.contracts import (
    LLMTurn,
    OrchestratorMessage,
    ToolCall,
    ToolCallingProvider,
    ToolCallOutput,
)
from src.services.anthropic_llm import (
    NGUONG_CACHE_KY_TU,
    AnthropicToolProvider,
    _to_anthropic,
    _to_anthropic_tools,
)
from src.services.llm import (
    ScriptedToolCallingProvider,
    _doc_luot_openai,
    _tham_so_model,
    _to_openai_tool_messages,
)

_SPEC_TOOL = {
    "type": "function",
    "function": {
        "name": "inventory_search",
        "description": "Tìm căn theo tiêu chí",
        "parameters": {"type": "object", "properties": {"phan_khu": {"type": "string"}}},
    },
}

_TRANSCRIPT = [
    OrchestratorMessage(role="user", content="tìm căn 2PN ở Ocean Park 2"),
    OrchestratorMessage(
        role="assistant",
        content="Để tôi tra tồn kho.",
        tool_calls=[ToolCall(id="call_1", name="inventory_search", arguments={"phan_khu": "OP2"})],
    ),
    OrchestratorMessage(
        role="tool",
        tool_outputs=[ToolCallOutput(call_id="call_1", content="Tìm thấy 3 căn.")],
    ),
]


class TestTuanThuProtocol:
    @pytest.mark.parametrize(
        "provider",
        [ScriptedToolCallingProvider(), AnthropicToolProvider("k", client=object())],
    )
    def test_cai_dung_giao_dien(self, provider: Any) -> None:
        assert isinstance(provider, ToolCallingProvider)


class TestDichSangOpenAI:
    def test_ket_qua_tool_thanh_message_vai_tool(self) -> None:
        tin = _to_openai_tool_messages(_TRANSCRIPT)

        assert tin[-1]["role"] == "tool"
        assert tin[-1]["tool_call_id"] == "call_1"

    def test_tham_so_tool_thanh_chuoi_json(self) -> None:
        """Chat Completions nhận `arguments` là CHUỖI, không phải dict."""
        tin = _to_openai_tool_messages(_TRANSCRIPT)
        goi = tin[1]["tool_calls"][0]

        assert isinstance(goi["function"]["arguments"], str)
        assert "OP2" in goi["function"]["arguments"]

    def test_doc_lai_duoc_luot_co_tool(self) -> None:
        phan_hoi = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="call_9",
                                function=SimpleNamespace(name="inventory_lookup", arguments='{"unit_code": "VOP397"}'),
                            )
                        ],
                    ),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=18),
        )

        luot = _doc_luot_openai(phan_hoi)

        assert luot.con_goi_tool
        assert luot.tool_calls[0].arguments == {"unit_code": "VOP397"}
        assert (luot.token_vao, luot.token_ra) == (120, 18)

    def test_tham_so_hong_thi_bo_chu_khong_no(self) -> None:
        """Model sinh JSON hỏng là chuyện có thật — không được làm đứt cả lượt."""
        phan_hoi = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="c1",
                                function=SimpleNamespace(name="x", arguments="{khong-phai-json"),
                            )
                        ],
                    ),
                )
            ],
            usage=None,
        )

        assert _doc_luot_openai(phan_hoi).tool_calls[0].arguments == {}


class TestDichSangAnthropic:
    def test_ket_qua_tool_nam_trong_vai_user(self) -> None:
        """Claude KHÔNG có vai "tool" — nhét sai vai là API trả 400."""
        tin = _to_anthropic(_TRANSCRIPT)

        assert tin[-1]["role"] == "user"
        assert tin[-1]["content"][0]["type"] == "tool_result"
        assert tin[-1]["content"][0]["tool_use_id"] == "call_1"

    def test_tham_so_tool_giu_nguyen_dict(self) -> None:
        """Ngược với OpenAI: Claude nhận `input` là dict, không phải chuỗi."""
        tin = _to_anthropic(_TRANSCRIPT)
        khoi = [k for k in tin[1]["content"] if k["type"] == "tool_use"][0]

        assert khoi["input"] == {"phan_khu": "OP2"}

    def test_doi_spec_tu_dinh_dang_openai(self) -> None:
        ra = _to_anthropic_tools([_SPEC_TOOL])

        assert ra[0]["name"] == "inventory_search"
        assert ra[0]["input_schema"]["properties"] == {"phan_khu": {"type": "string"}}

    def test_spec_thieu_parameters_van_hop_le(self) -> None:
        ra = _to_anthropic_tools([{"function": {"name": "x", "description": "y"}}])

        assert ra[0]["input_schema"] == {"type": "object", "properties": {}}


class TestThamSoGuiSonnet5:
    """Ba thứ riêng của Sonnet 5 — sai là 400 hoặc đội tiền."""

    def _tham_so(self, system: str = "prompt ngắn") -> dict[str, Any]:
        provider = AnthropicToolProvider("k", effort="low", client=object())
        return provider._dung_tham_so(system, _TRANSCRIPT, [_SPEC_TOOL], None, None)

    def test_khong_bao_gio_gui_temperature(self) -> None:
        """Sonnet 5 trả 400 khi nhận temperature khác mặc định."""
        assert "temperature" not in self._tham_so()

    def test_co_dat_effort(self) -> None:
        assert self._tham_so()["output_config"] == {"effort": "low"}

    def test_khong_gui_budget_tokens(self) -> None:
        """`budget_tokens` đã bị gỡ khỏi Sonnet 5, gửi lên là 400."""
        assert "budget_tokens" not in str(self._tham_so())

    def test_co_tool_thi_luon_danh_moc_cache(self) -> None:
        """Chốt chặn hồi quy cho một lỗi đo được trên máy thật.

        Bản đầu gác mốc bằng `len(system) >= 1024` — so số KÝ TỰ với ngưỡng tính
        bằng TOKEN, và chỉ đo mỗi system. Nhưng phần nặng nằm ở SPEC TOOL: đo
        thật thì 6 tool chiếm ~9.000 trong 10.184 token đầu vào. Mốc không bao
        giờ được đặt, và mọi lượt trả tiền đầy đủ cho phần bất biến.

        Thứ tự dựng prompt là tools → system → messages, nên một mốc ở khối
        system cuối cache được cả hai.
        """
        assert self._tham_so()["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_khong_tool_va_system_ngan_thi_khong_danh_moc(self) -> None:
        """Prefix quá ngắn thì Anthropic lặng lẽ bỏ qua — đánh mốc chỉ gây hiểu nhầm."""
        provider = AnthropicToolProvider("k", client=object())

        tham_so = provider._dung_tham_so("ngắn", [], [], None, None)

        assert "cache_control" not in tham_so["system"][0]

    def test_khong_tool_nhung_system_dai_thi_van_danh_moc(self) -> None:
        provider = AnthropicToolProvider("k", client=object())

        tham_so = provider._dung_tham_so("x" * (NGUONG_CACHE_KY_TU + 1), [], [], None, None)

        assert tham_so["system"][0]["cache_control"] == {"type": "ephemeral"}


class TestOrchestratorGiaLap:
    @pytest.mark.asyncio
    async def test_phat_lai_kich_ban_theo_thu_tu(self) -> None:
        provider = ScriptedToolCallingProvider(
            [
                LLMTurn(tool_calls=[ToolCall(id="1", name="inventory_search")]),
                LLMTurn(text="Có 3 căn phù hợp."),
            ]
        )

        dau = await provider.run_turn("s", [], tools=[])
        sau = await provider.run_turn("s", [], tools=[])

        assert dau.con_goi_tool
        assert sau.text == "Có 3 căn phù hợp."

    @pytest.mark.asyncio
    async def test_het_kich_ban_thi_dung_lai_chu_khong_quay_mai(self) -> None:
        provider = ScriptedToolCallingProvider()

        luot = await provider.run_turn("s", [], tools=[])

        assert not luot.con_goi_tool


class TestThamSoTheoHoModel:
    """Ba khác biệt giữa các thế hệ model OpenAI, cả ba đo được trên máy thật."""

    def test_luon_dung_ten_tham_so_moi(self) -> None:
        """`max_tokens` đã đổi thành `max_completion_tokens`; gpt-4o nhận cả hai."""
        for model in ("gpt-4o", "gpt-5.6-luna"):
            tham_so = _tham_so_model(model, None, 256)

            assert "max_tokens" not in tham_so
            assert "max_completion_tokens" in tham_so

    def test_ho_gpt5_khong_nhan_temperature(self) -> None:
        assert "temperature" not in _tham_so_model("gpt-5.6-luna", 0.0, 256)

    def test_model_cu_van_nhan_temperature(self) -> None:
        assert _tham_so_model("gpt-4o", 0.0, 256)["temperature"] == 0.0

    def test_model_suy_luan_co_san_han_muc(self) -> None:
        """Chốt chặn hồi quy cho lỗi HỎNG CÂM tốn nhiều thời gian nhất.

        Router đặt `max_tokens=10`. Trên gpt-5.6-luna thì cả 10 token đi vào
        phần suy luận không hiện ra, `content` về RỖNG, router coi là "nhãn lạ"
        rồi rơi về `general` — mà `general` không truy hồi, không tool, tức ngõ
        cụt tuyệt đối. Không có lỗi nào được ném ra để ai đó nhận biết.
        """
        assert _tham_so_model("gpt-5.6-luna", None, 10)["max_completion_tokens"] >= 1024

    def test_san_khong_lam_giam_han_muc_da_lon(self) -> None:
        assert _tham_so_model("gpt-5.6-luna", None, 4096)["max_completion_tokens"] == 4096

    def test_model_cu_giu_nguyen_han_muc_nho(self) -> None:
        """Model không suy luận thì 10 token là đủ cho một nhãn — đừng nâng thừa."""
        assert _tham_so_model("gpt-4o", None, 10)["max_completion_tokens"] == 10
