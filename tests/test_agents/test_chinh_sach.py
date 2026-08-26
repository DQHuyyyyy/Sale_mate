"""Cổng phân loại chính sách — chặn trước khi trả lời.

Không test nào gọi Anthropic thật: provider giả trả sẵn chuỗi JSON.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agents import chinh_sach
from src.agents.contracts import LLMTurn
from src.agents.nodes.chinh_sach import ChinhSachNode


class ProviderGia:
    """Trả sẵn một chuỗi, ghi lại prompt và đếm số lần bị gọi."""

    def __init__(self, tra_ve: str) -> None:
        self.tra_ve = tra_ve
        self.so_lan = 0
        self.prompt = ""

    async def run_turn(self, system, history, *, tools, model=None, max_tokens=None):  # noqa: ANN001, ARG002
        self.so_lan += 1
        self.prompt = history[0].content
        return LLMTurn(text=self.tra_ve)


class ProviderHong:
    """Mô phỏng ca đã xảy ra thật: tài khoản Anthropic chạm trần chi tiêu tháng."""

    async def run_turn(self, system, history, *, tools, model=None, max_tokens=None):  # noqa: ANN001, ARG002
        raise RuntimeError("nhà cung cấp sập")


async def _chay(provider, query: str) -> chinh_sach.KetQuaCong:
    return await chinh_sach.chot(chinh_sach.khoi_dong(provider, query, "m"))


# ---------- Phân loại ----------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nhan", "chan"),
    [("an_toan", True), ("ngoai_pham_vi", True), ("nhay_cam", False), ("binh_thuong", False)],
)
async def test_chi_hai_nhan_dau_chan(nhan: str, chan: bool) -> None:
    """`nhay_cam` chỉ gắn cờ, KHÔNG chặn — chặn nó là bỏ mất câu trả lời tốt hơn."""
    kq = await _chay(ProviderGia(f'{{"nhan": "{nhan}", "ly_do": "x"}}'), "câu hỏi")

    assert kq.nhan == nhan
    assert kq.chan is chan


@pytest.mark.asyncio
async def test_nhay_cam_co_co_rieng() -> None:
    kq = await _chay(ProviderGia('{"nhan": "nhay_cam", "ly_do": "đòi cam kết giá"}'), "giảm 5% nhé")

    assert kq.nhay_cam
    assert not kq.chan


# ---------- Hỏng thì cho đi tiếp, không chặn ----------


@pytest.mark.asyncio
async def test_provider_hong_thi_khong_chan() -> None:
    """Cổng hỏng mà chặn là biến sự cố nhà cung cấp thành từ chối mọi khách."""
    kq = await _chay(ProviderHong(), "câu hỏi")

    assert not kq.chan
    assert kq.loi


@pytest.mark.asyncio
@pytest.mark.parametrize("tho", ["không phải JSON", '{"nhan": "nhan_la"}', "{hỏng"])
async def test_ket_qua_rac_thi_khong_chan(tho: str) -> None:
    kq = await _chay(ProviderGia(tho), "câu hỏi")

    assert not kq.chan
    assert kq.nhan == chinh_sach.BINH_THUONG


# ---------- Không gọi model khi không cần ----------


@pytest.mark.asyncio
@pytest.mark.parametrize("cau", ["xin chào", "Chào!", "hi", "cảm ơn", "thanks"])
async def test_cau_xa_giao_khong_goi_model(cau: str) -> None:
    provider = ProviderGia('{"nhan": "binh_thuong"}')

    kq = await _chay(provider, cau)

    assert provider.so_lan == 0
    assert not kq.chan


@pytest.mark.asyncio
async def test_khong_co_provider_thi_khong_chan() -> None:
    assert chinh_sach.khoi_dong(None, "câu hỏi", "m") is None
    assert not (await chinh_sach.chot(None)).chan


# ---------- Node chỉ khởi động, KHÔNG chờ ----------


@pytest.mark.asyncio
async def test_node_tra_ve_ngay_khong_cho_ket_qua() -> None:
    """Node phải trả về task chưa xong — chờ ở đây là mất hết cái lợi song song."""

    class ProviderCham:
        async def run_turn(self, system, history, *, tools, model=None, max_tokens=None):  # noqa: ANN001, ARG002
            await asyncio.sleep(0.2)
            return LLMTurn(text='{"nhan": "binh_thuong"}')

    node = ChinhSachNode(ProviderCham(), model="m")
    ket_qua = await node({"query": "tìm căn 2PN"})
    task = ket_qua["chinh_sach_task"]

    assert not task.done()
    assert not (await chinh_sach.chot(task)).chan


# ---------- Lượt bám đuôi ----------


@pytest.mark.asyncio
async def test_cau_truoc_di_vao_prompt() -> None:
    """Lượt bám đuôi đứng riêng thì vô hại — cổng phải thấy câu trước mới chặn được.

    Đã xảy ra thật: "Hoàng Sa và Trường Sa của nước nào" rồi lượt sau gõ "góc độ
    lịch sử". Câu sau đứng một mình trông như câu hỏi bình thường.
    """
    provider = ProviderGia('{"nhan": "an_toan", "ly_do": "x"}')

    await chinh_sach.chot(chinh_sach.khoi_dong(provider, "góc độ lịch sử", "m", "Hoàng Sa của nước nào"))

    assert "</cau_truoc>" in provider.prompt
    assert "Hoàng Sa" in provider.prompt


@pytest.mark.asyncio
async def test_khong_co_cau_truoc_thi_khong_them_the_rong() -> None:
    provider = ProviderGia('{"nhan": "binh_thuong"}')

    await chinh_sach.chot(chinh_sach.khoi_dong(provider, "tìm căn 2PN", "m"))

    assert "</cau_truoc>" not in provider.prompt


@pytest.mark.asyncio
async def test_luot_bi_chan_van_co_nut_goi_y() -> None:
    """Người dùng vừa bị từ chối là lúc dễ rời đi nhất — phải có lối quay về."""
    assert chinh_sach.GOI_Y_SAU_KHI_CHAN
    assert all("căn" in g.lower() for g in chinh_sach.GOI_Y_SAU_KHI_CHAN)


def test_loi_tu_choi_dut_khoat_khong_noi_thieu_du_lieu() -> None:
    """'Chưa đủ dữ liệu' mời người dùng gửi thêm nguồn rồi hỏi lại — họ đã làm thật."""
    for loi in chinh_sach.LOI_TU_CHOI.values():
        assert "chưa có đủ dữ liệu" not in loi.lower()
        assert "ngoài phạm vi" in loi.lower()
