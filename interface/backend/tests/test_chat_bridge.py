"""Test cầu nối từ backend/ sang lõi AI ở src/.

Không gọi mạng thật: thay `httpx.AsyncClient` bằng transport giả của httpx.
"""

from __future__ import annotations

import asyncio
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


class TestGiuLoiAiThuc:
    """Giữ lõi AI khỏi ngủ trên gói free Render.

    Đây là tính năng TIÊU TIỀN gián tiếp: 750 giờ instance mỗi tháng cho cả
    workspace, giữ thức 24/7 hai service tốn ~48 giờ mỗi ngày. Bật quên tắt là
    Render treo toàn bộ service free tới đầu tháng sau. Nên phần lớn test ở đây
    canh chuyện "không tự bật", chứ không phải chuyện nó ping được.
    """

    def test_mac_dinh_phai_tat(self) -> None:
        """Chốt chặn quan trọng nhất của cả nhóm test này.

        Mặc định phải TẮT: ai clone repo về chạy local mà vô tình giữ thức một
        service trên Render là đốt hạn mức của cả team, và dấu hiệu duy nhất là
        web chết vào giữa tháng.
        """
        from app.core.config import Settings

        assert Settings(jwt_secret="x" * 40, database_url="postgresql://a/b").giu_loi_ai_thuc is False

    def test_chu_ky_cho_it_nhat_hai_luot_truoc_khi_ngu(self) -> None:
        """Render cho ngủ sau 15 phút.

        Chu kỳ phải đủ ngắn để có HAI lượt ping trong cửa sổ đó — một lượt hỏng
        vì Render trả 502 lúc bận vẫn còn lượt dự phòng. Vừa đúng 15 phút thì
        không có biên nào cả.
        """
        from app.core.config import Settings

        chu_ky = Settings(jwt_secret="x" * 40, database_url="postgresql://a/b").chu_ky_giu_thuc_giay
        assert chu_ky * 2 <= 15 * 60

    @pytest.mark.asyncio
    async def test_danh_thuc_nuot_loi_mang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lõi AI hỏng KHÔNG được làm hỏng phần còn lại của web.

        Hàm này chạy trong `lifespan`; ném lỗi ở đó là backend không khởi động
        được, tức mất cả danh sách căn và đăng nhập vì một tính năng phụ.
        """

        so_lan = {"goi": 0}

        def no(*_args: object, **_kwargs: object) -> None:
            so_lan["goi"] += 1
            raise httpx.ConnectError("khong noi duoc")

        async def ngu_gia(_giay: float) -> None:
            return None

        monkeypatch.setattr(chat_service.httpx, "AsyncClient", no)
        monkeypatch.setattr(chat_service.asyncio, "sleep", ngu_gia)
        await chat_service.danh_thuc_loi_ai()  # không được raise
        assert so_lan["goi"] == 3, "phải thử lại, không bỏ cuộc sau lượt đầu"

    @pytest.mark.asyncio
    async def test_thu_lai_khi_render_tra_502(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ca có thật trong log: 429 rồi 502 lúc Render đang dựng container.

        Lượt sau đó thành công. Bỏ cuộc ở lượt đầu là ngồi chờ trọn một chu kỳ
        nữa trong khi lõi AI vẫn ngủ.
        """
        ma: list[int] = [429, 502, 200]

        class Resp:
            def __init__(self, code: int) -> None:
                self.status_code = code

        class FakeClient:
            def __init__(self, **_kwargs: object) -> None: ...
            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_args: object) -> None: ...
            async def get(self, _url: str) -> Resp:
                return Resp(ma.pop(0))

        async def ngu_gia(_giay: float) -> None:
            return None

        monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeClient)
        monkeypatch.setattr(chat_service.asyncio, "sleep", ngu_gia)
        await chat_service.danh_thuc_loi_ai()
        assert ma == [], "phải thử tới khi được, không dừng ở 429"

    @pytest.mark.asyncio
    async def test_vong_lap_ngu_truoc_khi_ping_lan_dau(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`lifespan` đã ping một phát lúc khởi động rồi — ping lại ngay là thừa."""
        thu_tu: list[str] = []

        async def ngu_gia(_giay: float) -> None:
            thu_tu.append("ngu")
            if len(thu_tu) > 2:
                raise asyncio.CancelledError

        async def ping_gia() -> None:
            thu_tu.append("ping")

        monkeypatch.setattr(chat_service.asyncio, "sleep", ngu_gia)
        monkeypatch.setattr(chat_service, "danh_thuc_loi_ai", ping_gia)

        with pytest.raises(asyncio.CancelledError):
            await chat_service.vong_lap_giu_thuc()

        assert thu_tu[0] == "ngu"
        assert thu_tu[1] == "ping"

    @pytest.mark.asyncio
    async def test_mot_luot_ping_hong_khong_giet_vong_lap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lõi AI đang deploy lại thì vài phút nữa gọi được — đừng bỏ cuộc."""
        so_lan = {"ngu": 0}

        async def ngu_gia(_giay: float) -> None:
            so_lan["ngu"] += 1
            if so_lan["ngu"] > 3:
                raise asyncio.CancelledError

        async def ping_hong() -> None:
            raise RuntimeError("loi AI dang deploy")

        monkeypatch.setattr(chat_service.asyncio, "sleep", ngu_gia)
        monkeypatch.setattr(chat_service, "danh_thuc_loi_ai", ping_hong)

        with pytest.raises(asyncio.CancelledError):
            await chat_service.vong_lap_giu_thuc()

        assert so_lan["ngu"] > 3, "vòng lặp phải chạy tiếp sau lượt ping hỏng"
