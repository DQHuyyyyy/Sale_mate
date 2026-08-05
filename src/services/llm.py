"""Adapter ra LLM.

OpenAIProvider dùng thật; ScriptedProvider dùng cho test và cho trường hợp máy
chưa có API key (app vẫn chạy được, widget vẫn stream — chỉ là nội dung giả).
Cả hai cùng tuân LLMProvider Protocol nên đổi ở src/bootstrap.py là xong.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from openai import APIStatusError, AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.core.exceptions import LLMQuotaError, RateLimitError, SalesMateError, UpstreamError
from src.core.logging import get_logger
from src.models.chat import ChatMessage

logger = get_logger(__name__)


def _classify_rate_limit(exc: OpenAIRateLimitError) -> SalesMateError:
    """OpenAI trả 429 cho cả hai chuyện: gọi quá nhanh, và hết credit.

    Hai chuyện này xử lý khác hẳn nhau nên phải tách ra — nếu không, hết credit
    sẽ hiện thành "thử lại sau ít giây" và người dùng cứ thử mãi.
    """
    # SDK đặt code/type ngay trên exception; body là dict lỗi phẳng, không lồng
    # trong khoá "error". Đọc cả hai cho chắc khi SDK đổi.
    parts = [str(getattr(exc, "code", "") or ""), str(getattr(exc, "type", "") or "")]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        parts.append(str(body.get("code") or ""))
        parts.append(str(body.get("type") or ""))

    marker = " ".join(parts).lower()
    if "quota" in marker or "credit" in marker or "billing" in marker:
        logger.error("Tài khoản OpenAI hết credit")
        return LLMQuotaError()
    return RateLimitError()


class OpenAIProvider:
    """Gọi Chat Completions của OpenAI."""

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str = "gpt-4o-mini",
        timeout_s: float = 60.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._default_model = default_model
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_s)

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=model or self._default_model,
                messages=_to_openai(messages),
                temperature=temperature if temperature is not None else 0.3,
                max_tokens=max_tokens or 1024,
            )
        except OpenAIRateLimitError as exc:
            raise _classify_rate_limit(exc) from exc
        except APIStatusError as exc:
            logger.error("OpenAI trả lỗi %s", exc.status_code)
            raise UpstreamError("Dịch vụ AI đang bận. Vui lòng thử lại sau ít phút.") from exc

        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=model or self._default_model,
                messages=_to_openai(messages),
                temperature=temperature if temperature is not None else 0.3,
                max_tokens=max_tokens or 1024,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                token = chunk.choices[0].delta.content
                if token:
                    yield token
        except OpenAIRateLimitError as exc:
            raise _classify_rate_limit(exc) from exc
        except APIStatusError as exc:
            logger.error("OpenAI stream lỗi %s", exc.status_code)
            raise UpstreamError("Dịch vụ AI đang bận. Vui lòng thử lại sau ít phút.") from exc


class ScriptedProvider:
    """LLM giả lập — không gọi mạng.

    Dùng khi: chạy test, hoặc máy chưa cấu hình OPENAI_API_KEY. Trả về câu trả
    lời cố định, stream từng từ để FE vẫn thấy hiệu ứng gõ chữ thật.
    """

    DEFAULT_REPLY = (
        "Đây là phản hồi giả lập vì máy chưa cấu hình OPENAI_API_KEY. "
        "Điền khoá vào file .env rồi khởi động lại backend để dùng trợ lý thật."
    )

    def __init__(self, reply: str | None = None, *, delay_s: float = 0.02) -> None:
        self._reply = reply or self.DEFAULT_REPLY
        self._delay = delay_s

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return self._reply

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        for word in self._reply.split(" "):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield word + " "


def _to_openai(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role.value, "content": message.content} for message in messages]
