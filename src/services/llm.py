"""Adapter ra LLM.

OpenAIProvider dùng thật; ScriptedProvider dùng cho test và cho trường hợp máy
chưa có API key (app vẫn chạy được, widget vẫn stream — chỉ là nội dung giả).
Cả hai cùng tuân LLMProvider Protocol nên đổi ở src/bootstrap.py là xong.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import APIStatusError, AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError

from src.agents.contracts import LLMTurn, OrchestratorMessage, ToolCall
from src.core.exceptions import LLMQuotaError, RateLimitError, SalesMateError, UpstreamError
from src.core.logging import get_logger
from src.models.chat import ChatMessage

logger = get_logger(__name__)


@dataclass
class SoDoToken:
    """Cộng dồn token đã tiêu, tách theo model.

    CỐ Ý không đưa vào `LLMProvider` Protocol: hợp đồng đó đóng băng, và số đo
    chi phí là chuyện của tầng cài đặt chứ không phải điều kiện để gọi được LLM.
    Bên đo (`src/eval/answer.py`) dò bằng `getattr` nên provider nào không có bộ
    đếm vẫn chạy bình thường, chỉ là không có số.
    """

    vao: int = 0
    ra: int = 0
    theo_model: dict[str, list[int]] = field(default_factory=dict)  # model -> [vao, ra]

    def ghi_nhan(self, model: str, vao: int, ra: int) -> None:
        self.vao += vao
        self.ra += ra
        muc = self.theo_model.setdefault(model, [0, 0])
        muc[0] += vao
        muc[1] += ra

    def dat_lai(self) -> None:
        self.vao = 0
        self.ra = 0
        self.theo_model.clear()


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


# Họ model đã BỎ tham số lấy mẫu. Gửi `temperature` lên là 400, kể cả giá trị
# 0.0 — y hệt ràng buộc của Claude Sonnet 5.
#
# Hệ quả phải biết: router và plan vốn đặt `temperature=0.0` để phân nhãn tất
# định. Chạy trên họ model này thì tính tất định chỉ còn dựa vào prompt và mặc
# định của model. Đó là đánh đổi khi đổi model, không phải lỗi — nhưng đừng ngạc
# nhiên nếu cùng một câu thỉnh thoảng ra nhãn khác.
_HO_KHONG_NHAN_TEMPERATURE: tuple[str, ...] = ("gpt-5",)

# Sàn hạn mức đầu ra cho model SUY LUẬN.
#
# Đo được trên gpt-5.6-luna: token suy luận tính vào hạn mức đầu ra nhưng KHÔNG
# hiện ra nội dung. Router đặt `max_tokens=10` thì cả 10 token đi vào suy luận,
# `content` về rỗng, `finish_reason="length"` — và router coi đó là "nhãn lạ"
# rồi rơi về `general`. Mà `general` nằm trong `_KHONG_TRA_CUU`, nên câu hỏi
# thành ngõ cụt tuyệt đối: không truy hồi, không tool, không gì cả.
#
# Cùng câu đó với hạn mức 256 thì trả đúng nhãn sau 65 token suy luận.
#
# Nâng sàn gần như miễn phí: hạn mức là TRẦN, chỉ trả tiền cho token thật sự
# sinh ra. Đặt ở tầng adapter chứ không sửa từng chỗ gọi, để chỗ gọi mới thêm
# sau này cũng được bảo vệ.
_SAN_TOKEN_SUY_LUAN = 1024


def _tham_so_model(model: str, temperature: float | None, max_tokens: int | None) -> dict[str, Any]:
    """Ghép tham số hợp lệ cho ĐÚNG model đang gọi.

    Ba chỗ lệch nhau giữa các thế hệ model OpenAI. Hai cái đầu trả 400 nên khó
    bỏ sót; cái thứ ba HỎNG CÂM và tốn nhiều thời gian nhất để tìm ra:

    1. `max_tokens` đã đổi tên thành `max_completion_tokens`. Dùng tên mới cho
       tất cả — thế hệ cũ nhận được cả hai, nên một đường code là đủ.
    2. Họ `gpt-5` bỏ hẳn `temperature`.
    """
    tran = max_tokens or 1024
    if model.startswith(_HO_KHONG_NHAN_TEMPERATURE):
        # 3. Model suy luận đốt hạn mức đầu ra cho phần không hiện ra.
        return {"max_completion_tokens": max(tran, _SAN_TOKEN_SUY_LUAN)}

    return {
        "max_completion_tokens": tran,
        "temperature": temperature if temperature is not None else 0.3,
    }


class OpenAIProvider:
    """Gọi Chat Completions của OpenAI."""

    def __init__(
        self,
        api_key: str,
        *,
        # BẮT BUỘC truyền, KHÔNG có mặc định. Tên model chỉ được khai ở `.env`
        # rồi đi qua `Settings` — một mặc định ở đây là nơi thứ hai định nghĩa
        # model, và nó chỉ hiện ra khi wiring hỏng: lúc đó code lặng lẽ chạy một
        # model khác với thứ `.env` ghi. Thiếu tham số thì vỡ ngay lúc khởi động.
        default_model: str,
        timeout_s: float = 60.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._default_model = default_model
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_s)
        self.so_do_token = SoDoToken()

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        ten_model = model or self._default_model
        try:
            response = await self._client.chat.completions.create(
                model=ten_model,
                messages=_to_openai(messages),
                **_tham_so_model(ten_model, temperature, max_tokens),
            )
        except OpenAIRateLimitError as exc:
            raise _classify_rate_limit(exc) from exc
        except APIStatusError as exc:
            # Kèm nguyên văn: 400 vì tham số sai model trông y hệt 500 vì server
            # bận nếu chỉ log mã số, và hai chuyện đó xử lý khác hẳn nhau.
            logger.error("OpenAI trả lỗi %s cho model %s: %s", exc.status_code, ten_model, exc)
            raise UpstreamError("Dịch vụ AI đang bận. Vui lòng thử lại sau ít phút.") from exc

        self._ghi_nhan_token(ten_model, response)
        return response.choices[0].message.content or ""

    def _ghi_nhan_token(self, model: str, response: object) -> None:
        """Đọc `usage` nếu SDK có trả. Thiếu thì bỏ qua, không làm hỏng lượt gọi.

        Đường stream không đếm được: `usage` chỉ về ở chunk cuối và chỉ khi bật
        `stream_options`, mà bật lên là đổi hành vi của đường đang chạy thật.
        Bộ đo dùng `complete()` nên vẫn có số đầy đủ.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.so_do_token.ghi_nhan(
            model,
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0),
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        ten_model = model or self._default_model
        try:
            stream = await self._client.chat.completions.create(
                model=ten_model,
                messages=_to_openai(messages),
                stream=True,
                **_tham_so_model(ten_model, temperature, max_tokens),
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
            logger.error("OpenAI stream lỗi %s cho model %s: %s", exc.status_code, ten_model, exc)
            raise UpstreamError("Dịch vụ AI đang bận. Vui lòng thử lại sau ít phút.") from exc

    async def run_turn(
        self,
        system: str,
        history: list[OrchestratorMessage],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMTurn:
        """Cài `ToolCallingProvider` trên Chat Completions.

        Có mặt để orchestrator không bị khoá vào một nhà cung cấp: nếu Anthropic
        hỏng hoặc hết ngân sách, đổi một dòng ở `bootstrap.py` là vòng lặp chạy
        tiếp trên OpenAI. Cũng là cách đối chiếu hai model trên cùng một vòng lặp.
        """
        ten_model = model or self._default_model
        tin_nhan = [{"role": "system", "content": system}, *_to_openai_tool_messages(history)]
        try:
            response = await self._client.chat.completions.create(
                model=ten_model,
                messages=tin_nhan,
                tools=tools or None,
                # `None` = để helper tự quyết: model nào nhận temperature thì
                # dùng mặc định, họ `gpt-5` thì bỏ hẳn. Orchestrator không cần
                # cố định temperature nên không có gì phải giữ ở đây.
                **_tham_so_model(ten_model, None, max_tokens or 2048),
            )
        except OpenAIRateLimitError as exc:
            raise _classify_rate_limit(exc) from exc
        except APIStatusError as exc:
            logger.error("OpenAI tool calling lỗi %s cho model %s: %s", exc.status_code, ten_model, exc)
            raise UpstreamError("Dịch vụ AI đang bận. Vui lòng thử lại sau ít phút.") from exc

        self._ghi_nhan_token(ten_model, response)
        return _doc_luot_openai(response)


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


class ScriptedToolCallingProvider:
    """Orchestrator giả lập — phát lại một kịch bản lượt đã soạn sẵn.

    Có nó thì test được toàn bộ vòng lặp orchestrator (gọi tool, cộng bằng
    chứng, chạm trần lặp, lặp lại hành động) mà không tốn một đồng nào và không
    phụ thuộc mạng — đúng quy ước "không test nào gọi API thật".

    Hết kịch bản thì trả một lượt không còn tool call, tức vòng lặp kết thúc
    bình thường thay vì quay mãi.
    """

    def __init__(self, kich_ban: list[LLMTurn] | None = None) -> None:
        self._kich_ban = list(kich_ban or [])
        self.da_goi: list[list[OrchestratorMessage]] = []

    async def run_turn(
        self,
        system: str,
        history: list[OrchestratorMessage],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMTurn:
        self.da_goi.append(list(history))
        if self._kich_ban:
            return self._kich_ban.pop(0)
        return LLMTurn(text="Đã đủ dữ liệu để trả lời.", stop_reason="end_turn")


def _to_openai(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role.value, "content": message.content} for message in messages]


def _to_openai_tool_messages(history: list[OrchestratorMessage]) -> list[dict[str, Any]]:
    """Đổi transcript nội bộ sang định dạng Chat Completions.

    OpenAI đặt kết quả tool ở message vai "tool" riêng, mỗi kết quả một message
    — khác Claude gộp vào một message vai "user". Chính chỗ lệch này là lý do
    `OrchestratorMessage` tồn tại thay vì dùng thẳng kiểu của một SDK.
    """
    ra: list[dict[str, Any]] = []
    for luot in history:
        if luot.role == "tool":
            ra += [{"role": "tool", "tool_call_id": kq.call_id, "content": kq.content} for kq in luot.tool_outputs]
            continue

        tin: dict[str, Any] = {"role": luot.role, "content": luot.content or None}
        if luot.tool_calls:
            tin["tool_calls"] = [
                {
                    "id": goi.id,
                    "type": "function",
                    "function": {"name": goi.name, "arguments": json.dumps(goi.arguments)},
                }
                for goi in luot.tool_calls
            ]
        ra.append(tin)
    return ra


def _doc_luot_openai(response: Any) -> LLMTurn:
    lua_chon = response.choices[0]
    tin = lua_chon.message
    goi_tool = [
        ToolCall(id=goi.id, name=goi.function.name, arguments=_doc_json(goi.function.arguments))
        for goi in (tin.tool_calls or [])
    ]
    usage = getattr(response, "usage", None)
    return LLMTurn(
        text=(tin.content or "").strip(),
        tool_calls=goi_tool,
        stop_reason=str(lua_chon.finish_reason or ""),
        token_vao=int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
        token_ra=int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
    )


def _doc_json(tho: str | None) -> dict[str, Any]:
    """Tham số tool là chuỗi JSON do model sinh — hỏng thì bỏ, đừng để nổ."""
    if not tho:
        return {}
    try:
        da_doc = json.loads(tho)
    except json.JSONDecodeError:
        logger.warning("Tham số tool không phải JSON hợp lệ, bỏ qua")
        return {}
    return da_doc if isinstance(da_doc, dict) else {}
