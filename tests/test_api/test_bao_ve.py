"""Chốt chặn của lõi AI — khoá dịch vụ và phanh chi phí.

Lõi AI khai `type: web` trong `render.yaml` nên nó có URL công khai trên
Internet, và nó là chỗ gọi model, tức là chỗ tốn tiền. Trước khi có
`src/api/bao_ve.py`, `/api/v1/chat` không có `Depends` nào: ai biết URL đều gọi
thẳng được và bỏ qua toàn bộ hạn mức lẫn phân quyền của API sản phẩm.

Bộ test này khoá lại đúng hai câu hỏi đó: **ai** gọi được (401) và **bao nhiêu**
lượt (429).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.bao_ve import dat_lai_phanh
from src.core.config import Settings, get_settings
from src.main import app

KHOA = "khoa-dung-chung-chi-dung-trong-test"


def _cau_hinh(**ghi_de) -> Settings:
    mac_dinh = {"app_env": "test", "openai_api_key": ""}
    return Settings(_env_file=None, **{**mac_dinh, **ghi_de})  # type: ignore[call-arg]


@pytest.fixture
def dat_cau_hinh(configured_container):
    """Đè `get_settings` của app rồi trả về client — mỗi ca một cấu hình riêng."""

    def dung(**ghi_de):
        app.dependency_overrides[get_settings] = lambda: _cau_hinh(**ghi_de)
        dat_lai_phanh()
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield dung
    app.dependency_overrides.pop(get_settings, None)
    dat_lai_phanh()


class TestKhoaDichVu:
    @pytest.mark.asyncio
    async def test_khong_kem_khoa_thi_401(self, dat_cau_hinh) -> None:
        """Đây là chính ca mentor mô tả: gọi thẳng lõi AI, không xác thực gì."""
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            r = await client.post("/api/v1/chat", json={"message": "Xin chào"})

        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_khoa_sai_thi_401(self, dat_cau_hinh) -> None:
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            r = await client.post(
                "/api/v1/chat",
                json={"message": "Xin chào"},
                headers={"X-API-Key": KHOA + "x"},
            )

        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_khoa_dung_thi_qua(self, dat_cau_hinh) -> None:
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            r = await client.post(
                "/api/v1/chat",
                json={"message": "Xin chào"},
                headers={"X-API-Key": KHOA},
            )

        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_duong_stream_cung_bi_chan(self, dat_cau_hinh) -> None:
        """Widget dùng đường này, nên bỏ sót nó là bỏ sót toàn bộ lưu lượng thật."""
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            r = await client.post("/api/v1/chat/stream", json={"message": "Xin chào"})

        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_tai_lieu_cung_bi_chan(self, dat_cau_hinh) -> None:
        """Hồ sơ NỘI BỘ. `/api/tai-lieu` bên portal bắt đăng nhập đúng vì lý do
        đó — để hở ở tầng này là cái chặn kia thành trang trí."""
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            r = await client.get("/api/v1/documents")

        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_health_khong_bi_chan(self, dat_cau_hinh) -> None:
        """Render gọi `healthCheckPath` mà không cầm khoá nào. Chặn nó là service
        bị đánh dấu hỏng rồi khởi động lại vòng quanh."""
        async with dat_cau_hinh(ai_core_api_key=KHOA) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/api/v1/health")).status_code == 200


class TestKhoaChuaDat:
    @pytest.mark.asyncio
    async def test_production_thi_chan_het(self, dat_cau_hinh) -> None:
        """Cổng bảo vệ thất bại theo hướng MỞ thì nó không phải cổng.

        Quên khai biến trên Render là quay lại đúng trạng thái đang bị báo lỗi —
        mà lần này còn có một file tên `bao_ve.py` trong repo làm người đọc yên
        tâm. Cổng chính sách ngày 26/08/2026 đã hỏng đúng kiểu đó.
        """
        async with dat_cau_hinh(app_env="production", ai_core_api_key="") as client:
            r = await client.post("/api/v1/chat", json={"message": "Xin chào"})

        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_may_dev_thi_cho_qua(self, dat_cau_hinh) -> None:
        """`make run-ai` rồi mở /docs bấm thử phải chạy được — không thì mọi
        người sẽ tự tắt cổng đi cho đỡ vướng."""
        async with dat_cau_hinh(app_env="development", ai_core_api_key="") as client:
            r = await client.post("/api/v1/chat", json={"message": "Xin chào"})

        assert r.status_code == 200


class TestPhanhChiPhi:
    @pytest.mark.asyncio
    async def test_vuot_tran_thi_429(self, dat_cau_hinh) -> None:
        async with dat_cau_hinh(ai_core_api_key="", ai_core_rate_limit_per_minute=2) as client:
            ma = [(await client.post("/api/v1/chat", json={"message": "Xin chào"})).status_code for _ in range(3)]

        assert ma == [200, 200, 429]

    @pytest.mark.asyncio
    async def test_tran_khong_theo_ip(self, dat_cau_hinh) -> None:
        """Đếm cho CẢ tiến trình, cố tình khác `han_muc.py` bên portal.

        Người gọi hợp lệ duy nhất là API sản phẩm, tức mọi request đến từ một IP.
        Đếm theo IP thì hoặc trần rơi đúng vào lưu lượng thật, hoặc phải nới rộng
        tới mức vô nghĩa — thứ cần chặn ở tầng này là tổng chi tiêu chạy loạn.
        """
        async with dat_cau_hinh(ai_core_api_key="", ai_core_rate_limit_per_minute=1) as client:
            await client.post("/api/v1/chat", json={"message": "Xin chào"})
            r = await client.post(
                "/api/v1/chat",
                json={"message": "Xin chào"},
                headers={"X-Forwarded-For": "203.0.113.9"},
            )

        assert r.status_code == 429

    @pytest.mark.asyncio
    async def test_tra_ve_retry_after(self, dat_cau_hinh) -> None:
        async with dat_cau_hinh(ai_core_api_key="", ai_core_rate_limit_per_minute=1) as client:
            await client.post("/api/v1/chat", json={"message": "Xin chào"})
            r = await client.post("/api/v1/chat", json={"message": "Xin chào"})

        assert r.headers["Retry-After"]

    @pytest.mark.asyncio
    async def test_tran_0_la_tat(self, dat_cau_hinh) -> None:
        async with dat_cau_hinh(ai_core_api_key="", ai_core_rate_limit_per_minute=0) as client:
            ma = [(await client.post("/api/v1/chat", json={"message": "Xin chào"})).status_code for _ in range(4)]

        assert ma == [200, 200, 200, 200]

    @pytest.mark.asyncio
    async def test_khoa_sai_khong_ton_luot(self, dat_cau_hinh) -> None:
        """401 chạy trước phanh, nên người lạ gõ khoá bừa không đẩy được khách
        thật vào 429 — nếu ngược lại thì phanh chi phí thành công cụ tấn công."""
        async with dat_cau_hinh(ai_core_api_key=KHOA, ai_core_rate_limit_per_minute=2) as client:
            for _ in range(5):
                await client.post("/api/v1/chat", json={"message": "Xin chào"}, headers={"X-API-Key": "sai"})
            r = await client.post("/api/v1/chat", json={"message": "Xin chào"}, headers={"X-API-Key": KHOA})

        assert r.status_code == 200
