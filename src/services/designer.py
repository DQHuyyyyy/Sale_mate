"""Adapter ra model sửa ảnh.

Protocol đặt ở ĐÂY chứ không thêm vào `agents/contracts.py` — file đó đóng băng,
sửa phải mở PR riêng cho cả team review. Tính năng ảnh không đi qua agent graph
nên cũng không cần nằm trong hợp đồng của agent.

`OpenAIImageEditor` gọi thật; `FakeImageEditor` dùng cho test và cho máy chưa có
API key. Cùng một Protocol nên đổi ở `src/bootstrap.py` là xong.

KHÔNG test nào được gọi OpenAI thật — quy ước dự án. Đó là lý do bản giả tồn tại.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from openai import APIStatusError, AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.core.exceptions import LLMQuotaError, RateLimitError, UpstreamError
from src.core.logging import get_logger
from src.designer.pipeline import doc_anh, xuat_png
from src.designer.prompts import prompt_dinh_vi

logger = get_logger(__name__)


@runtime_checkable
class ImageEditor(Protocol):
    """Cổng ra model sửa ảnh. Nhận ảnh + mask + câu lệnh, trả ảnh PNG."""

    async def edit(self, *, anh: bytes, mask: bytes | None, lenh: str, kich_thuoc: str) -> bytes: ...


@runtime_checkable
class BoDinhVi(Protocol):
    """Cổng ra model THỊ GIÁC: đọc ảnh + câu lệnh, trả JSON khoanh vùng.

    Vì sao không dùng `LLMProvider` sẵn có: nó nhận `list[ChatMessage]`, mà
    `ChatMessage.content` là `str` thuần và `src/models/chat.py` đóng băng —
    không nhét ảnh vào được. Đây là cổng riêng, không đụng hợp đồng agent.

    Đây cũng là CHỐT CHI PHÍ: một lượt model rẻ đứng trước để loại yêu cầu mơ
    hồ, tránh đốt một lượt sinh ảnh đắt gấp nhiều lần vào thứ người dùng sẽ
    không ưng.
    """

    async def dinh_vi(self, *, anh: bytes, lenh: str) -> str: ...


class OpenAIBoDinhVi:
    """Dùng model rẻ có thị giác để khoanh vùng và chặn yêu cầu mơ hồ."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        timeout_s: float = 60.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_s)

    async def dinh_vi(self, *, anh: bytes, lenh: str) -> str:
        import base64

        url = f"data:image/png;base64,{base64.b64encode(anh).decode()}"
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=0.0,
                max_tokens=200,
                messages=[
                    {"role": "system", "content": prompt_dinh_vi()},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Yêu cầu: {lenh}"},
                            {"type": "image_url", "image_url": {"url": url}},
                        ],
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001 - biên ra ngoài
            logger.exception("Gọi model định vị vùng thất bại")
            raise UpstreamError("Không phân tích được ảnh.") from exc

        return response.choices[0].message.content or ""


class FakeBoDinhVi:
    """Bản giả — trả sẵn một kịch bản JSON, không chạm mạng."""

    MAC_DINH = '{"ro_rang": true, "thao_tac": "doi_thuoc_tinh", "doi_tuong": "rèm", "khung": [0.6, 0.1, 0.9, 0.7]}'

    def __init__(self, ket_qua: str = MAC_DINH) -> None:
        self._ket_qua = ket_qua
        self.so_lan_goi = 0

    async def dinh_vi(self, *, anh: bytes, lenh: str) -> str:  # noqa: ARG002
        self.so_lan_goi += 1
        return self._ket_qua


class OpenAIImageEditor:
    """Gọi endpoint images/edits.

    Lưu ý về `mask`: theo tài liệu OpenAI, vùng alpha = 0 là vùng ĐƯỢC SỬA, và
    mask chỉ là GỢI Ý — model vẫn vẽ lại cả khung ảnh. Bảo đảm "chỉ đổi phần
    được nhắc" nằm ở `images/pipeline.ghep_de`, không nằm ở đây.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-image-2",
        quality: str = "low",
        input_fidelity: str = "high",
        timeout_s: float = 120.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._quality = quality
        self._input_fidelity = input_fidelity
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_s)

    async def edit(self, *, anh: bytes, mask: bytes | None, lenh: str, kich_thuoc: str) -> bytes:
        # Không mask thì KHÔNG gửi khoá `mask` — gửi None là SDK vẫn dựng phần
        # multipart rỗng và API từ chối.
        tuy_chon: dict[str, Any] = {}
        if mask is not None:
            tuy_chon["mask"] = ("mask.png", mask, "image/png")
        # Chỉ gửi khi được khai rõ: gpt-image-2 trả 400 nếu thấy tham số này.
        if self._input_fidelity:
            tuy_chon["input_fidelity"] = self._input_fidelity

        try:
            response = await self._client.images.edit(
                model=self._model,
                image=("anh.png", anh, "image/png"),
                prompt=lenh,
                size=kich_thuoc,
                quality=self._quality,
                n=1,
                **tuy_chon,
            )
        except OpenAIRateLimitError as exc:
            # Cùng luật với services/llm.py: 429 vừa là "gọi quá nhanh" vừa là
            # "hết credit", hai chuyện xử lý khác hẳn nhau.
            marker = f"{getattr(exc, 'code', '')} {getattr(exc, 'type', '')}".lower()
            raise (LLMQuotaError() if "quota" in marker or "billing" in marker else RateLimitError()) from exc
        except APIStatusError as exc:
            raise _tu_choi(exc) from exc
        except Exception as exc:  # noqa: BLE001 - biên ra ngoài, gói thành lỗi nghiệp vụ
            logger.exception("Gọi model sửa ảnh thất bại")
            raise UpstreamError("Không gọi được model sửa ảnh.") from exc

        return _lay_bytes(response)


def _tu_choi(exc: APIStatusError) -> UpstreamError:
    """Đọc lý do OpenAI từ chối, ghi log đầy đủ, trả thông điệp đúng loại lỗi.

    Bản trước nuốt sạch: mọi lỗi 4xx đều thành "Model sửa ảnh từ chối yêu cầu
    này." Người dùng không biết phải làm gì, và người sửa code cũng không —
    trong khi API đã nói rõ ràng "The model 'gpt-image-2' does not support the
    'input_fidelity' parameter". Mất nguyên một lượt gỡ lỗi vì câu đó bị vứt đi.

    Phân biệt hai loại vì cách xử lý khác hẳn nhau: sai tham số là LỖI CỦA
    CHÚNG TA, người dùng có thử lại bao nhiêu lần cũng vậy.
    """
    loi = exc.body if isinstance(exc.body, dict) else {}
    thong_diep = str(loi.get("message") or exc)
    param = str(loi.get("param") or "")

    logger.error(
        "OpenAI từ chối sửa ảnh (HTTP %s, param=%s): %s",
        exc.status_code,
        param or "-",
        thong_diep,
    )

    if param:
        # Người dùng không cần biết tên tham số, nhưng phải biết đây không phải
        # lỗi của họ và thử lại cũng vô ích.
        return UpstreamError("Tính năng sửa ảnh đang cấu hình sai. Lỗi đã được ghi lại, bạn thử lại sau nhé.")

    return UpstreamError("Mình không chỉnh được ảnh theo yêu cầu này. Bạn thử diễn đạt cách khác xem.")


def _lay_bytes(response: object) -> bytes:
    """Rút ảnh khỏi response. SDK trả base64 trong `data[0].b64_json`."""
    import base64

    data = getattr(response, "data", None) or []
    if not data:
        raise UpstreamError("Model sửa ảnh không trả về ảnh nào.")

    b64 = getattr(data[0], "b64_json", None)
    if not b64:
        raise UpstreamError("Model sửa ảnh trả về dữ liệu không đọc được.")
    return base64.b64decode(b64)


class FakeImageEditor:
    """Bản giả — trả lại chính ảnh đầu vào, đã đổi màu nhẹ để test phân biệt được.

    Cố ý KHÔNG trả ảnh trắng: test cần thấy pipeline ghép đúng vùng, mà ảnh
    trắng thì không phân biệt nổi "ghép sai chỗ" với "ghép đúng chỗ".
    """

    def __init__(self, *, mau: tuple[int, int, int] = (0, 0, 255)) -> None:
        self._mau = mau
        self.so_lan_goi = 0
        self.lenh_cuoi = ""
        self.kich_thuoc_cuoi = ""
        self.mask_cuoi: bytes | None = None

    async def edit(self, *, anh: bytes, mask: bytes | None, lenh: str, kich_thuoc: str) -> bytes:
        self.so_lan_goi += 1
        self.lenh_cuoi = lenh
        self.kich_thuoc_cuoi = kich_thuoc
        self.mask_cuoi = mask

        from PIL import Image

        goc = doc_anh(anh)
        return xuat_png(Image.new("RGB", goc.size, self._mau))
