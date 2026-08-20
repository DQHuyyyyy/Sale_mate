"""Test bộ đếm chi phí và phanh ngân sách ngày.

Phanh này là thứ đứng giữa một buổi debug và $5 ngân sách Anthropic. Nó phải
đúng ở hai đầu: chặn khi vượt, và KHÔNG chặn nhầm khi chưa cấu hình.
"""

from __future__ import annotations

import pytest

from src.agents.contracts import LLMTurn
from src.agents.nodes.orchestrate import OrchestratorNode
from src.agents.state import initial_state
from src.agents.tools.registry import ToolRegistry
from src.core.chi_phi import SoChiTieu, so_chi_tieu
from src.services.llm import ScriptedToolCallingProvider


@pytest.fixture(autouse=True)
def _dat_lai_bo_dem():
    """Bộ đếm là singleton toàn tiến trình — mỗi test phải bắt đầu từ 0."""
    so_chi_tieu.dat_lai()
    yield
    so_chi_tieu.dat_lai()


class TestSoChiTieu:
    def test_cong_don_theo_gia_that(self) -> None:
        so = SoChiTieu()

        so.ghi_nhan("claude-sonnet-5", token_vao=1_000_000, token_ra=0)

        assert so.tom_tat()["da_tieu_usd"] == pytest.approx(2.0)

    def test_tran_bang_khong_nghia_la_khong_gioi_han(self) -> None:
        """Biến môi trường thiếu sẽ về 0 — mặc định không được tắt âm thầm tính năng."""
        so = SoChiTieu()
        so.ghi_nhan("claude-sonnet-5", token_vao=10_000_000, token_ra=10_000_000)

        assert so.con_ngan_sach(0.0) is True

    def test_chan_khi_vuot_tran(self) -> None:
        so = SoChiTieu()

        assert so.con_ngan_sach(1.0) is True
        so.ghi_nhan("claude-sonnet-5", token_vao=1_000_000, token_ra=0)  # $2.00
        assert so.con_ngan_sach(1.0) is False

    def test_model_thieu_gia_khong_lam_hong_bo_dem(self) -> None:
        """Không biết giá thì không cộng — nhưng cũng không được nổ."""
        so = SoChiTieu()

        so.ghi_nhan("model-moi-toanh", token_vao=999, token_ra=999)

        assert so.tom_tat()["da_tieu_usd"] == 0.0


class TestPhanhTrongOrchestrator:
    def _node(self, tran: float) -> OrchestratorNode:
        provider = ScriptedToolCallingProvider([LLMTurn(text="xong", token_vao=1_000_000, token_ra=0)])
        return OrchestratorNode(
            provider,
            registry=ToolRegistry(),
            ngan_sach_ngay_usd=tran,
            model="claude-sonnet-5",
        )

    @pytest.mark.asyncio
    async def test_luot_dau_chay_luot_sau_bi_phanh(self) -> None:
        state = initial_state("tìm căn 2PN", "s1")
        state["needs_retrieval"] = True

        dau = await self._node(1.0)(state)
        sau = await self._node(1.0)(state)

        assert dau["leo_thang"] == "R1"
        assert sau["leo_thang"] == ""

    @pytest.mark.asyncio
    async def test_bi_phanh_thi_khong_bao_loi_ra_ngoai(self) -> None:
        """Khách vẫn phải nhận câu trả lời từ đường tất định, không phải một lỗi."""
        state = initial_state("tìm căn 2PN", "s1")
        state["needs_retrieval"] = True
        await self._node(1.0)(state)

        ket_qua = await self._node(1.0)(state)

        assert "error" not in ket_qua
        assert ket_qua["orchestrator_loi"] == "hết ngân sách ngày"
