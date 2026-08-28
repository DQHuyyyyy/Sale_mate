"""Cấu hình đọc từ biến môi trường. Không hardcode secret ở bất kỳ đâu khác."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
# backend/ nằm trong interface/, nên gốc repo lùi thêm một cấp nữa.
REPO_DIR = BACKEND_DIR.parents[1]


class Settings(BaseSettings):
    # Một file .env duy nhất cho cả repo. Trước đây còn đọc thêm backend/.env
    # đè lên file này; bỏ đi vì file thứ hai chỉ chứa placeholder chưa ai điền
    # và nó ghi đè mất giá trị thật ở .env gốc, khiến backend không khởi động.
    model_config = SettingsConfigDict(
        env_file=REPO_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Database ----
    database_url: str = ""

    # ---- Supabase Storage ----
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "apartment-images"

    # ---- Auth ----
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # ---- Chatbot ----
    # Lõi AI nằm ở src/ (agent graph + RAG + trích nguồn), chạy như một service
    # riêng. backend/ không gọi thẳng OpenAI nữa — OPENAI_API_KEY thuộc về lõi AI.
    ai_core_url: str = "http://localhost:8001"
    ai_core_timeout: float = 60.0
    # Khoá dùng chung với lõi AI. PHẢI trùng `AI_CORE_API_KEY` của service kia —
    # lệch thì mọi câu hỏi trả 401 và người dùng nhận "Câu hỏi gửi lên không hợp
    # lệ", một thông điệp đúng mã lỗi nhưng dẫn đi sai hướng hoàn toàn.
    #
    # Rỗng thì không gửi header nào; chỉ chạy được khi lõi AI cũng để rỗng, tức
    # ở máy dev. Xem `src/api/bao_ve.py`.
    ai_core_api_key: str = ""

    # Hạn mức cho các endpoint AI TỐN TIỀN — /api/chat và /api/images/modify.
    # Mặc định BẬT: chúng công khai và mỗi lượt đều tốn tiền model, tắt trên môi
    # trường có người ngoài truy cập là mở cửa cho người lạ tiêu quota. Chỉ tắt
    # khi tự test.
    chat_rate_limit_enabled: bool = True

    # ---- Sinh ảnh (Modify Object) ----
    # Sửa ảnh nội thất theo yêu cầu người dùng. Ảnh KHÔNG được lưu — chỉ trả về
    # cho phiên chat đang mở, vì đây là ảnh minh hoạ do AI tạo, không phải ảnh
    # thật của căn.
    #
    # Đổi nhà cung cấp bằng biến môi trường, không sửa code — cùng nguyên tắc
    # `bootstrap.py` của lõi AI dùng cho LLM và vector store.
    image_provider: Literal["openai", "gemini", "seedream"] = "openai"
    image_timeout_s: float = 300.0

    # OPENAI_API_KEY vốn "thuộc về lõi AI" (xem mục Chatbot ở trên). Tính năng
    # này là ngoại lệ có chủ đích: nó không phải hỏi đáp nên không đi qua lõi AI,
    # mà vẫn cần một key sinh ảnh. Dùng lại key sẵn có đỡ được một thứ phải cấu
    # hình trên Render và một hoá đơn phải theo dõi.
    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1-mini"
    # "auto" để model tự giữ khổ ảnh gốc. Ép "1024x1024" thì ảnh căn hộ (khổ
    # ngang) bị cắt hoặc bóp méo — đo được: ảnh gốc 1023x767, `auto` trả về
    # 1536x1024 đúng tỉ lệ.
    openai_image_size: str = "auto"

    google_api_key: str = ""
    gemini_image_model: str = "gemini-3.1-flash-image"

    # Seedream 4.0 qua BytePlus ModelArk. Khoá dạng `ark-...`, KHÁC key OpenAI —
    # đây là nhà cung cấp thứ ba, không dùng chung khoá với ai.
    ark_api_key: str = ""
    seedream_model: str = "seedream-4-0-250828"
    # "2K" để model tự chọn cạnh theo TỈ LỆ ảnh gốc — đo thật: gửi ảnh 768x512
    # (3:2) thì nhận về 2496x1664, đúng 3:2. Ép một cỡ cố định thì ảnh căn hộ
    # khổ ngang bị cắt hoặc bóp méo, cùng lý do `openai_image_size` để "auto".
    seedream_size: str = "2K"
    # Dấu "AI generated" ByteDance đóng ở góc phải dưới. TẮT mặc định để đổi nhà
    # cung cấp không đổi diện mạo ảnh — GPT và Gemini đều không đóng dấu.
    #
    # Đáng cân nhắc bật: nhãn "Ảnh minh hoạ do AI tạo" của giao diện nằm TRÊN
    # TRANG, không nằm trong ảnh. Sale lưu ảnh gửi Zalo cho khách thì nhãn rơi
    # lại, chỉ còn tấm ảnh — và khách nhìn thấy một căn hộ có nội thất mà căn
    # thật không có. Watermark là thứ duy nhất đi theo được file ảnh.
    #
    # Đổi bằng biến môi trường, không phải deploy lại.
    seedream_watermark: bool = False

    @property
    def image_edit_key(self) -> str:
        return {
            "openai": self.openai_api_key,
            "gemini": self.google_api_key,
            "seedream": self.ark_api_key,
        }[self.image_provider]

    @property
    def image_edit_enabled(self) -> bool:
        return bool(self.image_edit_key)

    # ---- App ----
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def chat_enabled(self) -> bool:
        return bool(self.ai_core_url)

    def config_problems(self) -> list[str]:
        """Vấn đề cấu hình chặn khởi động. Rỗng nghĩa là chạy được."""
        problems = []
        if not self.database_url:
            problems.append("DATABASE_URL chưa đặt — backend không kết nối được Supabase.")
        if not self.jwt_secret:
            problems.append("JWT_SECRET chưa đặt.")
        elif len(self.jwt_secret) < 32:
            problems.append(
                "JWT_SECRET ngắn hơn 32 ký tự nên dễ bị dò. Sinh chuỗi mới bằng: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return problems


settings = Settings()
