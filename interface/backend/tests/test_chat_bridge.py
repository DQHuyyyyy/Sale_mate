"""Test cầu nối từ backend/ sang lõi AI ở src/.

Không gọi mạng thật: thay `httpx.AsyncClient` bằng transport giả của httpx.
"""

from __future__ import annotations

import os

import httpx
import pytest
from pydantic import ValidationError

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.schemas.chat import ChatMessage, ChatRequest  # noqa: E402
from app.services import chat as chat_service  # noqa: E402


def _fake_client(handler: httpx.MockTransport) -> type:
    """Trả về lớp thay cho httpx.AsyncClient, gắn sẵn transport giả."""

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            kwargs.pop("timeout", None)
            super().__init__(transport=handler)

    return FakeAsyncClient


@pytest.fixture
def goi_loi_ai(monkeypatch: pytest.MonkeyPatch):
    """Bắt request gửi sang lõi AI và trả về response do test quy định."""
    ghi_nhan: dict[str, object] = {}

    def dung(status_code: int, body: object) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            ghi_nhan["url"] = str(request.url)
            ghi_nhan["body"] = request.content.decode()
            ghi_nhan["headers"] = dict(request.headers)
            return httpx.Response(status_code, json=body)

        monkeypatch.setattr(chat_service.httpx, "AsyncClient", _fake_client(httpx.MockTransport(handler)))

    dung.ghi_nhan = ghi_nhan  # type: ignore[attr-defined]
    return dung


class TestGenerateReply:
    @pytest.mark.asyncio
    async def test_tra_ve_cau_tra_loi_cua_loi_ai(self, goi_loi_ai) -> None:
        goi_loi_ai(200, {"message": "  Căn 2 phòng ngủ còn 3 căn.  ", "session_id": "s1"})

        ket_qua = await chat_service.generate_reply("Còn căn nào không?", [])

        assert ket_qua == "Căn 2 phòng ngủ còn 3 căn."

    @pytest.mark.asyncio
    async def test_goi_dung_endpoint_va_gui_du_lich_su(self, goi_loi_ai) -> None:
        goi_loi_ai(200, {"message": "ok", "session_id": "s1"})

        await chat_service.generate_reply(
            "Giá bao nhiêu?",
            [ChatMessage(role="user", content="Chào"), ChatMessage(role="assistant", content="Chào bạn")],
        )

        assert goi_loi_ai.ghi_nhan["url"].endswith("/api/v1/chat")
        assert "Chào bạn" in str(goi_loi_ai.ghi_nhan["body"])

    @pytest.mark.asyncio
    async def test_gui_lai_session_id_de_log_gom_ve_mot_phien(self, goi_loi_ai) -> None:
        goi_loi_ai(200, {"message": "ok", "session_id": "s1"})

        await chat_service.generate_reply("Câu thứ hai", [], "phien-abc")

        assert "phien-abc" in str(goi_loi_ai.ghi_nhan["body"])

    @pytest.mark.asyncio
    async def test_khong_co_session_id_thi_khong_gui_khoa_do(self, goi_loi_ai) -> None:
        """Gửi None sẽ khiến lõi AI nhận session_id=null thay vì tự sinh."""
        goi_loi_ai(200, {"message": "ok", "session_id": "s1"})

        await chat_service.generate_reply("Câu đầu", [])

        assert "session_id" not in str(goi_loi_ai.ghi_nhan["body"])

    @pytest.mark.asyncio
    async def test_loi_ai_tra_400_thi_khong_bao_la_dang_ban(self, goi_loi_ai) -> None:
        """4xx là request sai — bảo người dùng 'thử lại sau' là đẩy vào vòng vô ích."""
        goi_loi_ai(422, {"detail": "sai body"})

        with pytest.raises(chat_service.ChatError) as loi:
            await chat_service.generate_reply("Hỏi gì đó", [])

        assert "không hợp lệ" in str(loi.value)

    @pytest.mark.asyncio
    async def test_loi_ai_tra_loi_500_thi_bao_loi_co_noi_dung(self, goi_loi_ai) -> None:
        goi_loi_ai(500, {"detail": "sap"})

        with pytest.raises(chat_service.ChatError) as loi:
            await chat_service.generate_reply("Hỏi gì đó", [])

        assert "Thử lại" in str(loi.value)

    @pytest.mark.asyncio
    async def test_phan_hoi_sai_dinh_dang_thi_khong_lam_sap_router(self, goi_loi_ai) -> None:
        goi_loi_ai(200, {"khong_co_truong_message": True})

        with pytest.raises(chat_service.ChatError):
            await chat_service.generate_reply("Hỏi gì đó", [])

    @pytest.mark.asyncio
    async def test_chua_cau_hinh_ai_core_url_thi_bao_ro_cach_khac_phuc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(chat_service.settings, "ai_core_url", "")

        with pytest.raises(chat_service.ChatError) as loi:
            await chat_service.generate_reply("Hỏi gì đó", [])

        assert "AI_CORE_URL" in str(loi.value)


class TestKhoaDichVu:
    """Lõi AI có URL công khai trên Render nên nó chặn request không cầm khoá.

    Quên gửi header ở đây thì mọi câu hỏi trên production trả 401 và người dùng
    nhận "Câu hỏi gửi lên không hợp lệ" — đúng mã lỗi, sai hoàn toàn về nguyên
    nhân, và không ai nghĩ tới việc đi so hai biến môi trường.
    """

    @pytest.mark.asyncio
    async def test_gui_kem_khoa_khi_da_cau_hinh(self, goi_loi_ai, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(chat_service.settings, "ai_core_api_key", "khoa-test")
        goi_loi_ai(200, {"message": "ok", "session_id": "s1"})

        await chat_service.generate_reply("Hỏi gì đó", [])

        assert goi_loi_ai.ghi_nhan["headers"]["x-api-key"] == "khoa-test"

    @pytest.mark.asyncio
    async def test_khong_gui_header_rong(self, goi_loi_ai, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rỗng thì bỏ hẳn header. Gửi `X-API-Key: ""` là gửi một khoá SAI, và
        lõi AI từ chối nó — trong khi ý định là "máy dev, chưa đặt khoá"."""
        monkeypatch.setattr(chat_service.settings, "ai_core_api_key", "")
        goi_loi_ai(200, {"message": "ok", "session_id": "s1"})

        await chat_service.generate_reply("Hỏi gì đó", [])

        assert "x-api-key" not in goi_loi_ai.ghi_nhan["headers"]


class TestRangBuocDoDai:
    """Trần 2000 ký tự áp cho câu người dùng gõ, KHÔNG áp cho lịch sử.

    Lỗi đã xảy ra thật: trợ lý liệt kê 23 căn còn bán, câu trả lời đó dài hơn
    2000 ký tự. Nó nằm lại trong lịch sử, nên MỌI lượt hỏi sau đều bị chặn ở
    422 "String should have at most 2000 characters" — người dùng không gõ gì
    quá dài mà cuộc hội thoại vẫn hỏng vĩnh viễn, không cách nào tự thoát.
    """

    def test_cau_tra_loi_dai_trong_lich_su_van_gui_duoc(self) -> None:
        tra_loi_dai = "Căn VOP758: 1PN, 54,5m2, 3,55 tỷ. " * 200
        assert len(tra_loi_dai) > 2000

        yeu_cau = ChatRequest(
            message="Phân tích chi tiết căn VOP619",
            history=[
                {"role": "user", "content": "Còn căn nào ở Ocean Park 1?"},
                {"role": "assistant", "content": tra_loi_dai},
            ],
        )

        assert yeu_cau.history[1].content == tra_loi_dai

    def test_cau_nguoi_dung_go_van_bi_chan_o_2000(self) -> None:
        """Trần cho `message` phải còn — nó khớp bộ đếm x/2000 ở widget."""
        with pytest.raises(ValidationError):
            ChatRequest(message="a" * 2001, history=[])

    def test_lich_su_rong_van_bi_chan(self) -> None:
        """Bỏ max_length không được kéo theo bỏ min_length."""
        with pytest.raises(ValidationError):
            ChatRequest(message="chào", history=[{"role": "user", "content": ""}])
