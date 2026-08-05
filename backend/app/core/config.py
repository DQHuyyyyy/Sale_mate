"""Cấu hình đọc từ biến môi trường. Không hardcode secret ở bất kỳ đâu khác."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # Đọc REPO/.env trước, backend/.env sau — file sau ghi đè file trước,
    # nên biến đặt riêng cho backend luôn thắng.
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
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
