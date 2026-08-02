"""Lỗi nghiệp vụ và ánh xạ sang HTTP status.

Code trong src/ chỉ raise các lớp ở đây, KHÔNG raise HTTPException trực tiếp —
nhờ vậy tầng agent/data không phải biết gì về HTTP và test được độc lập.
src/api/errors.py lo việc đổi chúng thành response.
"""

from __future__ import annotations


class SalesMateError(Exception):
    """Lỗi gốc của hệ thống. Mọi lỗi nghiệp vụ kế thừa từ đây."""

    code: str = "internal_error"
    status_code: int = 500
    default_message: str = "Đã xảy ra lỗi. Vui lòng thử lại."

    def __init__(self, message: str | None = None, *, detail: dict | None = None) -> None:
        self.message = message or self.default_message
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        payload: dict = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return {"error": payload}


class ValidationFailedError(SalesMateError):
    code = "validation_failed"
    status_code = 422
    default_message = "Dữ liệu gửi lên không hợp lệ."


class UnauthorizedError(SalesMateError):
    code = "unauthorized"
    status_code = 401
    default_message = "Bạn cần đăng nhập để thực hiện thao tác này."


class ForbiddenError(SalesMateError):
    code = "forbidden"
    status_code = 403
    default_message = "Bạn không có quyền truy cập nội dung này."


class NotFoundError(SalesMateError):
    code = "not_found"
    status_code = 404
    default_message = "Không tìm thấy nội dung bạn yêu cầu."


class RateLimitError(SalesMateError):
    code = "rate_limit"
    status_code = 429
    default_message = "Bạn thao tác hơi nhanh. Vui lòng thử lại sau ít giây."


class UpstreamError(SalesMateError):
    """Dịch vụ ngoài (LLM, Qdrant, DB) lỗi."""

    code = "upstream_error"
    status_code = 502
    default_message = "Dịch vụ bên ngoài đang gặp sự cố. Vui lòng thử lại sau."


class LLMQuotaError(SalesMateError):
    """Tài khoản LLM hết credit — lỗi vận hành, không phải lỗi người dùng.

    Tách khỏi RateLimitError vì cách xử lý khác hẳn: rate limit thì chờ rồi thử
    lại, hết credit thì phải nạp tiền, thử lại bao nhiêu lần cũng vô ích.
    """

    code = "llm_quota_exhausted"
    status_code = 503
    default_message = (
        "Tài khoản AI đã hết credit nên trợ lý tạm thời chưa trả lời được. Vui lòng báo quản trị viên nạp thêm credit."
    )


class AgentTimeoutError(SalesMateError):
    code = "agent_timeout"
    status_code = 504
    default_message = "Trợ lý xử lý quá lâu. Vui lòng thử lại với câu hỏi ngắn hơn."


class ConfigurationError(SalesMateError):
    """Sai cấu hình — lỗi của người vận hành, không phải của người dùng."""

    code = "configuration_error"
    status_code = 500
    default_message = "Hệ thống chưa được cấu hình đúng. Vui lòng báo quản trị viên."


class InsufficientContextError(SalesMateError):
    """Độ phủ truy hồi thấp — agent phải từ chối thay vì suy đoán."""

    code = "insufficient_context"
    status_code = 200  # Không phải lỗi HTTP: đây là câu trả lời hợp lệ "chưa đủ dữ liệu".
    default_message = "Chưa đủ dữ liệu để trả lời chính xác câu hỏi này."
