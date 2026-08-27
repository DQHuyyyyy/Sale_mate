"""Adapter ra Claude, dùng cho orchestrator.

Tách khỏi `llm.py` có chủ ý: `llm.py` nằm trên đường đi chung của MỌI lượt hỏi,
còn SDK `anthropic` chỉ cần cho nhánh leo thang. Để chung một file thì máy nào
chưa `pip install anthropic` sẽ hỏng import ngay từ `bootstrap`, tức một tính
năng phụ làm chết cả trợ lý. Tách ra thì import lỗi chỉ tắt đúng phần leo thang.

Ba điều riêng của Claude Sonnet 5, sai là hỏng hoặc đội tiền:

1. KHÔNG gửi `temperature`. Sonnet 5 trả 400 khi nhận giá trị khác mặc định.
   Đây là lý do router vẫn phải chạy trên OpenAI — chỗ đó cần `temperature=0.0`
   để phân nhãn tất định.
2. Adaptive thinking BẬT MẶC ĐỊNH và token suy nghĩ tính theo giá đầu ra
   ($10/1M). `effort` là cần ga chính; mặc định dự án đặt "low".
3. `cache_control` đặt trên khối system cuối. System prompt + spec của 6 tool là
   phần đầu ổn định của mọi lượt, cache lại thì đọc rẻ đi 10 lần.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.contracts import (
    LLMTurn,
    OrchestratorMessage,
    ToolCall,
)
from src.core.exceptions import LLMQuotaError, RateLimitError, UpstreamError
from src.core.logging import get_logger

logger = get_logger(__name__)

# Anthropic chỉ cache prefix từ ~1024 token trở lên; ngắn hơn thì đánh dấu
# `cache_control` cũng không tạo mục cache nào — im lặng, không báo lỗi.
#
# Ngưỡng dưới đây tính bằng KÝ TỰ và chỉ dùng cho trường hợp KHÔNG có tool.
# 4 ký tự ~ 1 token với văn bản Latin, nhưng tiếng Việt có dấu tốn hơn, nên
# đây là ước lượng thận trọng: đặt nhầm mốc chỉ mất tác dụng cache, không sai
# kết quả. Có tool thì khỏi ước lượng — spec tool luôn vượt ngưỡng.
NGUONG_CACHE_KY_TU = 4096


def _to_anthropic(history: list[OrchestratorMessage]) -> list[dict[str, Any]]:
    """Đổi transcript nội bộ sang định dạng Messages API.

    Claude nhận kết quả tool dưới dạng `tool_result` nằm trong message vai
    "user" — khác OpenAI (vai "tool" riêng). Chỗ khác nhau này là lý do lớp
    `OrchestratorMessage` tồn tại thay vì dùng thẳng kiểu của một SDK.
    """
    ket_qua: list[dict[str, Any]] = []
    for luot in history:
        if luot.role == "tool":
            ket_qua.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": ra.call_id,
                            "content": ra.content,
                            "is_error": ra.is_error,
                        }
                        for ra in luot.tool_outputs
                    ],
                }
            )
            continue

        khoi: list[dict[str, Any]] = []
        if luot.content:
            khoi.append({"type": "text", "text": luot.content})
        khoi += [
            {"type": "tool_use", "id": goi.id, "name": goi.name, "input": goi.arguments} for goi in luot.tool_calls
        ]
        if khoi:
            ket_qua.append({"role": luot.role, "content": khoi})
    return ket_qua


def _to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Đổi spec kiểu OpenAI (`{"type":"function","function":{...}}`) sang kiểu Claude.

    Nhận kiểu OpenAI vì `AgentTool.spec()` đã sinh sẵn định dạng đó và nó đang
    được dùng ở chỗ khác. Đổi ở đây rẻ hơn là sửa `spec()` — sửa `spec()` là
    đụng vào hợp đồng `AgentTool` mà mọi tool đang kế thừa.
    """
    ra = []
    for tool in tools:
        ham = tool.get("function", tool)
        ra.append(
            {
                "name": ham["name"],
                "description": ham.get("description", ""),
                "input_schema": ham.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return ra


class AnthropicToolProvider:
    """Cài `ToolCallingProvider` trên Claude Messages API."""

    def __init__(
        self,
        api_key: str,
        *,
        # BẮT BUỘC truyền, KHÔNG có mặc định — cùng lý do với `OpenAIProvider`:
        # tên model chỉ khai ở `.env`, một mặc định ở đây là nơi thứ hai định
        # nghĩa nó và chỉ lộ ra khi wiring đã hỏng.
        default_model: str,
        effort: str = "low",
        max_tokens: int = 4096,
        timeout_s: float = 120.0,
        client: Any = None,
    ) -> None:
        self._default_model = default_model
        self._effort = effort
        self._max_tokens = max_tokens
        self._client = client or self._dung_client(api_key, timeout_s)

    @staticmethod
    def _dung_client(api_key: str, timeout_s: float) -> Any:
        # Import trong hàm: máy chưa cài SDK vẫn import được module này, lỗi chỉ
        # nổ đúng lúc ai đó thật sự muốn dùng orchestrator.
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
            raise UpstreamError(
                "Chưa cài SDK anthropic. Chạy: pip install anthropic — hoặc tắt ENABLE_ORCHESTRATOR."
            ) from exc
        return AsyncAnthropic(api_key=api_key, timeout=timeout_s)

    async def run_turn(
        self,
        system: str,
        history: list[OrchestratorMessage],
        *,
        tools: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMTurn:
        tham_so = self._dung_tham_so(system, history, tools, model, max_tokens)
        try:
            phan_hoi = await self._client.messages.create(**tham_so)
        except Exception as exc:  # noqa: BLE001 - biên ra ngoài, phân loại rồi ném lại
            raise self._doi_loi(exc) from exc

        return self._doc_phan_hoi(phan_hoi)

    def _dung_tham_so(
        self,
        system: str,
        history: list[OrchestratorMessage],
        tools: list[dict[str, Any]],
        model: str | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """Ghép body. CỐ Ý không có `temperature` — Sonnet 5 trả 400 vì nó."""
        khoi_system: list[dict[str, Any]] = [{"type": "text", "text": system}]

        # Đánh mốc cache lên khối system CUỐI. Thứ tự dựng prompt là
        # tools → system → messages, nên một mốc ở đây cache CẢ spec tool lẫn
        # system — và spec tool mới là phần nặng: đo trên máy thật, 6 tool của
        # dự án chiếm ~9.000 trong 10.184 token đầu vào của một lượt.
        #
        # Bản đầu gác điều kiện bằng `len(system) >= 1024` và nó SAI hai lần:
        # so số KÝ TỰ với ngưỡng tính bằng TOKEN, và chỉ đo mỗi system trong khi
        # phần quyết định độ dài prefix nằm ở tools. Kết quả là mốc không bao giờ
        # được đặt, và mọi lượt đều trả tiền đầy đủ cho 9.000 token bất biến.
        if tools or len(system) >= NGUONG_CACHE_KY_TU:
            khoi_system[0]["cache_control"] = {"type": "ephemeral"}

        return {
            "model": model or self._default_model,
            "max_tokens": max_tokens or self._max_tokens,
            "system": khoi_system,
            "messages": _to_anthropic(history),
            "tools": _to_anthropic_tools(tools),
            "output_config": {"effort": self._effort},
        }

    @staticmethod
    def _doc_phan_hoi(phan_hoi: Any) -> LLMTurn:
        chu: list[str] = []
        goi_tool: list[ToolCall] = []
        for khoi in getattr(phan_hoi, "content", []) or []:
            loai = getattr(khoi, "type", "")
            if loai == "text":
                chu.append(getattr(khoi, "text", ""))
            elif loai == "tool_use":
                goi_tool.append(
                    ToolCall(
                        id=getattr(khoi, "id", ""),
                        name=getattr(khoi, "name", ""),
                        arguments=_doc_input(getattr(khoi, "input", None)),
                    )
                )

        usage = getattr(phan_hoi, "usage", None)
        return LLMTurn(
            text="".join(chu).strip(),
            tool_calls=goi_tool,
            stop_reason=str(getattr(phan_hoi, "stop_reason", "") or ""),
            token_vao=int(getattr(usage, "input_tokens", 0) or 0) if usage else 0,
            token_ra=int(getattr(usage, "output_tokens", 0) or 0) if usage else 0,
            token_doc_cache=int(getattr(usage, "cache_read_input_tokens", 0) or 0) if usage else 0,
            token_ghi_cache=int(getattr(usage, "cache_creation_input_tokens", 0) or 0) if usage else 0,
        )

    @staticmethod
    def _doi_loi(exc: Exception) -> Exception:
        """Đổi lỗi SDK sang lỗi nghiệp vụ của dự án.

        Dò theo TÊN lớp thay vì import lớp lỗi: module này phải import được cả
        khi chưa cài SDK, mà `except AnthropicRateLimitError` thì cần import ở
        đầu file.

        Tách HẾT CREDIT khỏi các lỗi tạm thời — cùng bài học đã học ở
        `_classify_rate_limit` cho OpenAI. Hết credit là lỗi VĨNH VIỄN: thử lại
        bao nhiêu lần cũng vậy, và gộp nó vào "đang bận, thử lại sau" thì người
        vận hành đi đọc log mạng thay vì đi nạp tiền. Anthropic trả nó dưới dạng
        400 `invalid_request_error` chứ không phải 429, nên chỉ dò tên lớp là
        không đủ — phải đọc cả nội dung thông điệp.
        """
        ten = type(exc).__name__
        noi_dung = str(exc).lower()

        if any(dau in noi_dung for dau in ("credit balance", "billing", "quota")):
            logger.error("Tài khoản Anthropic hết credit — nhánh leo thang sẽ không chạy được")
            return LLMQuotaError()
        if "RateLimit" in ten or "rate_limit" in noi_dung:
            logger.warning("Anthropic giới hạn tốc độ")
            return RateLimitError()

        logger.error("Anthropic lỗi %s: %s", ten, exc)
        return UpstreamError("Trợ lý chưa xử lý được câu hỏi nhiều bước này.")


def _doc_input(tho: Any) -> dict[str, Any]:
    """Tham số tool phải là dict. Model trả kiểu khác thì bỏ, đừng để nổ."""
    if isinstance(tho, dict):
        return tho
    if isinstance(tho, str):
        try:
            da_doc = json.loads(tho)
        except json.JSONDecodeError:
            logger.warning("Tham số tool không phải JSON hợp lệ, bỏ qua")
            return {}
        return da_doc if isinstance(da_doc, dict) else {}
    return {}
