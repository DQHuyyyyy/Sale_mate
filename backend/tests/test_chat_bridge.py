"""Test cầu nối từ backend/ sang lõi AI ở src/.

Không gọi mạng thật: thay `httpx.AsyncClient` bằng transport giả của httpx.
"""

from __future__ import annotations

import os

import httpx
import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-chi-dung-trong-test-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.schemas.chat import ChatMessage  # noqa: E402
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
