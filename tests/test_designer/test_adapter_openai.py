"""Test adapter gọi OpenAI — dùng client giả, KHÔNG chạm mạng.

Sinh ra từ một lỗi thật: tôi gửi `input_fidelity` cho `gpt-image-2`, model này
trả 400 và cả tính năng chết. Không test nào bắt được vì mọi test khác đều dùng
`FakeImageEditor`, tức là bỏ qua đúng chỗ dựng tham số gửi đi.

Bài học rộng hơn: bản giả cho phép test logic, nhưng KHÔNG kiểm được hợp đồng
với API thật. Chỗ nào dựng tham số cho bên ngoài thì phải test riêng chỗ đó.
"""

from __future__ import annotations

import io

import pytest
from openai import APIStatusError
from PIL import Image

from src.core.exceptions import UpstreamError
from src.services.designer import OpenAIImageEditor


def _anh() -> bytes:
    bo_dem = io.BytesIO()
    Image.new("RGB", (32, 32), (180, 170, 160)).save(bo_dem, format="PNG")
    return bo_dem.getvalue()


class _Ket:
    def __init__(self, b64: str = "") -> None:
        self.b64_json = b64 or _b64_anh()


def _b64_anh() -> str:
    import base64

    return base64.b64encode(_anh()).decode()


class _ClientGia:
    """Ghi lại tham số truyền xuống SDK thay vì gọi thật."""

    def __init__(self, loi: Exception | None = None) -> None:
        self.tham_so: dict = {}
        self._loi = loi
        self.images = self

    async def edit(self, **kwargs):
        self.tham_so = kwargs
        if self._loi:
            raise self._loi
        return type("R", (), {"data": [_Ket()]})()


def _editor(client: _ClientGia, **kwargs) -> OpenAIImageEditor:
    return OpenAIImageEditor("khoa-gia", client=client, **kwargs)


class TestInputFidelity:
    @pytest.mark.asyncio
    async def test_de_trong_thi_khong_gui_tham_so(self):
        """gpt-image-2 trả 400 nếu thấy `input_fidelity` — không được gửi."""
        client = _ClientGia()

        await _editor(client, input_fidelity="").edit(anh=_anh(), mask=None, lenh="x", kich_thuoc="1024x1024")

        assert "input_fidelity" not in client.tham_so

    @pytest.mark.asyncio
    async def test_khai_ro_thi_moi_gui(self):
        """Đổi sang gpt-image-1.5 thì bật lại được mà không phải sửa code."""
        client = _ClientGia()

        await _editor(client, input_fidelity="high").edit(anh=_anh(), mask=None, lenh="x", kich_thuoc="1024x1024")

        assert client.tham_so["input_fidelity"] == "high"


class TestMask:
    @pytest.mark.asyncio
    async def test_khong_mask_thi_khong_co_khoa_mask(self):
        """Gửi mask=None là SDK vẫn dựng phần multipart rỗng và API từ chối."""
        client = _ClientGia()

        await _editor(client).edit(anh=_anh(), mask=None, lenh="x", kich_thuoc="1024x1024")

        assert "mask" not in client.tham_so

    @pytest.mark.asyncio
    async def test_co_mask_thi_gui_kem(self):
        client = _ClientGia()

        await _editor(client).edit(anh=_anh(), mask=_anh(), lenh="x", kich_thuoc="1024x1024")

        assert client.tham_so["mask"][0] == "mask.png"


class TestThongDiepLoi:
    """Thông điệp phải nói rõ chuyện gì — bản trước nuốt sạch nguyên nhân."""

    @staticmethod
    def _loi(body: dict) -> APIStatusError:
        import httpx

        return APIStatusError(
            "400",
            response=httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com")),
            body=body,
        )

    @pytest.mark.asyncio
    async def test_sai_tham_so_thi_noi_ro_la_loi_cau_hinh(self):
        """Người dùng thử lại bao nhiêu lần cũng vậy — phải nói cho họ biết."""
        loi = self._loi(
            {
                "message": "The model 'gpt-image-2' does not support the 'input_fidelity' parameter.",
                "param": "input_fidelity",
            }
        )
        client = _ClientGia(loi)

        with pytest.raises(UpstreamError, match="cấu hình sai"):
            await _editor(client).edit(anh=_anh(), mask=None, lenh="x", kich_thuoc="1024x1024")

    @pytest.mark.asyncio
    async def test_tu_choi_noi_dung_thi_moi_bao_dien_dat_lai(self):
        client = _ClientGia(self._loi({"message": "Your request was rejected by our safety system."}))

        with pytest.raises(UpstreamError, match="diễn đạt cách khác"):
            await _editor(client).edit(anh=_anh(), mask=None, lenh="x", kich_thuoc="1024x1024")
