"""Cấu hình tập trung, nạp từ biến môi trường / file .env.

Quy tắc: KHÔNG module nào đọc os.environ trực tiếp — luôn đi qua get_settings().
Nhờ vậy test có thể ghi đè cấu hình ở một chỗ duy nhất.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Toàn bộ cấu hình chạy được của ứng dụng."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- App ----------
    app_name: str = "SalesMate"
    app_env: Environment = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    cors_origins: str = "http://localhost:3000"

    # ---------- LLM ----------
    # Hai tầng model: model rẻ cho router/phân loại, model mạnh cho câu trả lời.
    openai_api_key: str = ""
    llm_model_answer: str = "gpt-4o"
    llm_model_fast: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, gt=0)
    llm_timeout_s: float = Field(default=60.0, gt=0)

    # ---------- Vector store ----------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "documents_chunks"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = Field(default=1536, gt=0)

    # ---------- Retrieval ----------
    # Tắt RAG thì agent trả lời bằng kiến thức chung của model, không tra tài
    # liệu và không trích nguồn — chỉ dùng khi cần chẩn đoán, không dùng khi demo.
    enable_rag: bool = True
    retrieval_top_k: int = Field(default=20, gt=0)
    rerank_top_n: int = Field(default=5, gt=0)
    # Dưới ngưỡng này coi như "chưa đủ dữ liệu" — agent phải từ chối thay vì đoán.
    coverage_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    # keyword: không cần thư viện ngoài, chạy được ở mọi nơi kể cả Render free.
    # cross_encoder: chính xác hơn nhưng kéo theo sentence-transformers + torch
    # (~2GB) — xem docs/adr/ADR-002 về lý do không đưa vào phụ thuộc mặc định.
    reranker: Literal["keyword", "cross_encoder", "passthrough"] = "keyword"

    # ---------- Vòng lặp agent ----------
    # Bật thì agent tự quyết gọi tool nào, lặp tối đa `agent_max_iterations`
    # lượt để gom đủ dữ kiện. Tắt thì chạy đường tất định cũ: router → tools →
    # retrieve → generate, mỗi node đúng một lần.
    #
    # Mặc định TẮT. Vòng lặp tốn thêm lượt gọi model và có thể trả lời chậm hơn;
    # bật ở dev trước, đo rồi mới bật production. Tắt được bằng biến môi trường
    # là cứu hoả không cần deploy lại.
    enable_agent_loop: bool = False
    # Trần cứng, không phải gợi ý. Không có nó thì một câu hỏi xấu đốt sạch quota:
    # model cứ thấy thiếu dữ liệu là gọi thêm tool, gọi mãi.
    agent_max_iterations: int = Field(default=2, ge=1, le=5)

    # ---------- Database ----------
    database_url: str = "sqlite:///./data/app.db"

    # ---------- Supabase ----------
    # anon_key dùng được ở phía trình duyệt (bị RLS chặn).
    # service_role_key BỎ QUA MỌI RLS — chỉ dùng ở server, không bao giờ gửi ra FE.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "apartment-images"

    # ---------- Chat ----------
    chat_max_chars: int = Field(default=2000, gt=0)
    chat_history_limit: int = Field(default=10, ge=0)

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS ở .env là chuỗi ngăn cách bởi dấu phẩy."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def uses_supabase(self) -> bool:
        return "supabase" in self.database_url

    @property
    def uses_qdrant_cloud(self) -> bool:
        return "cloud.qdrant.io" in self.qdrant_url

    @property
    def use_real_vector_store(self) -> bool:
        """Có nối vào Qdrant thật không.

        Môi trường test luôn dùng store trong bộ nhớ — không test nào được gọi
        Qdrant thật, vừa chậm vừa phụ thuộc mạng vừa làm bẩn dữ liệu chung.
        """
        return bool(self.qdrant_url) and not self.is_test

    @property
    def has_openai_key(self) -> bool:
        """Không có key thật thì hệ thống rơi về LLM giả lập (xem src/bootstrap.py)."""
        return bool(self.openai_api_key) and not self.openai_api_key.startswith(("sk-your", "test"))


@lru_cache
def get_settings() -> Settings:
    """Trả về Settings dạng singleton (cache theo process)."""
    return Settings()
