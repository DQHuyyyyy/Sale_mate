"""Test cơ chế tự gọi tool: binding trong registry và ToolsNode.

Dùng registry RIÊNG cho từng test thay vì bảng toàn cục — thêm tool thật vào
bảng chung sẽ làm test này phụ thuộc vào việc dự án có bao nhiêu tool.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.contracts import AgentTool, ToolResult
from src.agents.nodes.tools import ToolsNode
from src.agents.state import Intent
from src.agents.tools.registry import ToolRegistry, register_tool
from src.agents.tools.registry import registry as global_registry


class _EchoTool(AgentTool):
    """Tool giả trả lại đúng tham số nhận được."""

    name = "echo"
    description = "Tool thử. Câu thứ hai không được vào title."

    def __init__(self, *, ok: bool = True, data: Any = None) -> None:
        self._ok = ok
        self._data = data if data is not None else [{"unit_code": "VOP345", "price_label": "2,7 tỷ"}]

    async def run(self, **kwargs: Any) -> ToolResult:
        if not self._ok:
            return ToolResult.failure("hỏng có chủ đích")
        return ToolResult(ok=True, data=self._data, source="test:db")


def _registry_with(tool: AgentTool, *, intents=(Intent.LISTING,), build_args=None) -> ToolRegistry:
    reg = ToolRegistry()
    reg.add(tool, _binding(intents, build_args or (lambda q: {"q": q})))
    return reg


def _binding(intents, build_args):
    from src.agents.tools.registry import ToolBinding

    return ToolBinding(intents=frozenset(intents), build_args=build_args)


# ---------- Registry ----------


def test_binding_loc_theo_intent():
    reg = _registry_with(_EchoTool(), intents=(Intent.LISTING,))

    assert [t.name for t, _ in reg.for_intent(Intent.LISTING)] == ["echo"]
    assert reg.for_intent(Intent.LEGAL) == []
    assert reg.for_intent(None) == []


def test_tool_dang_ky_tran_thi_khong_tu_goi():
    """Vẫn nằm trong registry cho LLM thấy, nhưng agent không tự chạy."""
    reg = ToolRegistry()
    reg.add(_EchoTool())

    assert reg.get("echo") is not None
    assert reg.for_intent(Intent.LISTING) == []


def test_khai_intents_ma_thieu_build_args_thi_bao_loi_ngay():
    with pytest.raises(ValueError, match="build_args"):

        @register_tool(intents={Intent.LISTING})
        class _Thieu(AgentTool):
            name = "thieu_build_args"

            async def run(self, **kwargs: Any) -> ToolResult:
                return ToolResult(ok=True, data=[])


def test_decorator_dang_tran_van_chay_duoc():
    """Dạng `@register_tool` không ngoặc phải giữ nguyên hành vi cũ."""
    assert global_registry.get("inventory_lookup") is not None


# ---------- ToolsNode ----------


@pytest.mark.asyncio
async def test_khong_co_tool_nao_nhan_intent_thi_tra_rong():
    node = ToolsNode(_registry_with(_EchoTool(), intents=(Intent.LISTING,)))

    out = await node({"intent": Intent.LEGAL, "query": "thủ tục sang tên"})

    assert out["tool_context"] == ""
    assert out["tool_citations"] == []


@pytest.mark.asyncio
async def test_build_args_tra_none_thi_tool_khong_chay():
    """Tầng lọc tinh: cùng intent nhưng câu hỏi không đủ dữ kiện."""
    node = ToolsNode(_registry_with(_EchoTool(), build_args=lambda q: None))

    out = await node({"intent": Intent.LISTING, "query": "tìm căn 2 phòng ngủ"})

    assert out["tool_context"] == ""


@pytest.mark.asyncio
async def test_chay_tool_va_dua_so_lieu_vao_context():
    node = ToolsNode(_registry_with(_EchoTool()))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP345"})

    assert "VOP345" in out["tool_context"]
    assert "2,7 tỷ" in out["tool_context"]


@pytest.mark.asyncio
async def test_nguon_tu_tool_lay_ma_can_lam_nhan():
    """Nhãn nguồn phải là thứ người đọc KIỂM CHỨNG được, tức mã căn.

    Bản cũ lấy câu đầu trong description ("Tool thử") — đúng kỹ thuật nhưng
    người đọc không tra lại được gì từ nó, và nút bấm mở căn cũng không có chỗ
    bám. Đây cũng là danh sách FE dựng dòng "Nguồn" khi model bỏ qua luật trích
    dẫn, nên nó phải khớp đúng thứ model lẽ ra đã trích.
    """
    node = ToolsNode(_registry_with(_EchoTool()))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP345"})

    citation = out["tool_citations"][0]
    assert citation.kind == "db"
    assert citation.doc_id == "test:db"
    assert citation.title == "VOP345"


@pytest.mark.asyncio
async def test_khong_co_ma_can_thi_lui_ve_ten_tool():
    """Tool không trả căn nào (tính khoản vay, tra chính sách) vẫn phải có nguồn.

    Nhãn là TÊN tool, không phải câu đầu trong `description`: mô tả viết cho
    model đọc, không viết cho khách. Dòng "Nguồn" từng hiện nguyên "Đếm số căn
    còn trống / đã bán trong tồn kho, tổng hợp theo toà và loại căn".
    """

    class _KhongCoMaCan(_EchoTool):
        async def run(self, **kwargs):
            return ToolResult(ok=True, data={"so_tien_vay": 1.5}, source="test:db")

    node = ToolsNode(_registry_with(_KhongCoMaCan()))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP345"})

    assert out["tool_citations"][0].title == "echo"


@pytest.mark.asyncio
async def test_tool_khai_nhan_nguon_thi_dung_nhan_do():
    """`nhan_nguon` cho tool tổng hợp một nhãn người đọc hiểu được."""

    class _CoNhan(_EchoTool):
        nhan_nguon = "Dữ liệu tồn kho"

        async def run(self, **kwargs):
            return ToolResult(ok=True, data={"con_trong": 30}, source="test:db")

    node = ToolsNode(_registry_with(_CoNhan()))

    out = await node({"intent": Intent.LISTING, "query": "còn bao nhiêu căn"})

    assert out["tool_citations"][0].title == "Dữ liệu tồn kho"


@pytest.mark.asyncio
async def test_tool_hong_thi_khong_lam_dut_luong():
    node = ToolsNode(_registry_with(_EchoTool(ok=False)))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP345"})

    assert out["tool_context"] == ""
    assert "error" not in out


@pytest.mark.asyncio
async def test_tool_khong_tim_thay_gi_thi_khong_dung_context():
    """Rỗng KHÁC hỏng: không được bịa ra context từ danh sách trống."""
    node = ToolsNode(_registry_with(_EchoTool(data=[])))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP999"})

    assert out["tool_context"] == ""


@pytest.mark.asyncio
async def test_mot_tool_hong_khong_chan_tool_con_lai():
    reg = ToolRegistry()
    reg.add(_EchoTool(ok=False), _binding((Intent.LISTING,), lambda q: {"q": q}))

    class _Khac(_EchoTool):
        name = "khac"

    reg.add(_Khac(), _binding((Intent.LISTING,), lambda q: {"q": q}))

    out = await ToolsNode(reg)({"intent": Intent.LISTING, "query": "căn VOP345"})

    assert "VOP345" in out["tool_context"]
    assert len(out["tool_citations"]) == 1


@pytest.mark.asyncio
async def test_node_van_do_thoi_gian_chay():
    """ToolsNode không được trả sẵn khoá metadata — sẽ nuốt số đo của BaseNode."""
    node = ToolsNode(_registry_with(_EchoTool()))

    out = await node({"intent": Intent.LISTING, "query": "căn VOP345", "metadata": {}})

    assert "tools_ms" in out["metadata"]
