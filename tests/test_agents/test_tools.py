"""Test registry và tool tồn kho (mock)."""

from __future__ import annotations

import pytest

from src.agents.tools import registry
from src.agents.tools.inventory import InventoryLookupTool


def test_tool_tu_dang_ky_vao_registry():
    assert registry.get("inventory_lookup") is not None


def test_registry_khong_cho_trung_ten():
    with pytest.raises(ValueError, match="trùng tên"):
        registry.add(InventoryLookupTool())


def test_spec_co_du_thong_tin_cho_llm():
    spec = registry.get("inventory_lookup").spec()

    assert spec["function"]["name"] == "inventory_lookup"
    assert "project" in spec["function"]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tra_ton_kho_theo_du_an():
    result = await InventoryLookupTool().run(project="Lakeside Metropole")

    assert result.ok
    assert len(result.data) == 2
    assert result.data[0]["status_label"] == "Còn trống"


@pytest.mark.asyncio
async def test_tra_ton_kho_loc_theo_loai_can():
    result = await InventoryLookupTool().run(project="Lakeside Metropole", unit_type="3PN")

    assert [row["unit_code"] for row in result.data] == ["A-15-02"]


@pytest.mark.asyncio
async def test_khong_khop_thi_tra_rong_chu_khong_no():
    result = await InventoryLookupTool().run(project="Dự án không tồn tại")

    assert result.ok
    assert result.data == []
    assert result.error


@pytest.mark.asyncio
async def test_tham_so_sai_thi_tra_failure_khong_raise():
    """Tool không bao giờ ném lỗi ra ngoài — agent tự quyết định xử lý."""
    result = await InventoryLookupTool().run(building="A")

    assert result.ok is False
    assert "không hợp lệ" in result.error
