"""Cấu hình tập trung, nạp từ biến môi trường / file .env.

Quy tắc: KHÔNG module nào đọc os.environ trực tiếp — luôn đi qua get_settings().
Nhờ vậy test có thể ghi đè cấu hình ở một chỗ duy nhất.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.logging import get_logger

logger = get_logger(__name__)

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
    # Thư mục nhật ký theo phiên. Rỗng = tắt. Đã nằm trong .gitignore nên nội
    # dung không bao giờ lên git — đây là chỗ theo dõi ở máy mình, không phải
    # dữ liệu chia sẻ. Terminal vẫn hiện bản ngắn; file giữ đầy đủ ở mức DEBUG.
    log_dir: str = "logs"
    cors_origins: str = "http://localhost:3000"

    # ---------- LLM ----------
    # Hai tầng model: model rẻ cho router/phân loại, model mạnh cho câu trả lời.
    openai_api_key: str = ""
    # Cùng một model cho cả hai tầng, $0.20/$1.20 mỗi triệu token.
    #
    # Khâu TRẢ LỜI từng bị khoá ở một model đắt hơn hẳn: đây là chỗ duy nhất có
    # hồi quy thật khi hạ model — bản rẻ trước đó bỏ mất toà/tầng/phòng và bỏ
    # luôn luật trích nguồn, nên dòng "Nguồn" biến mất trên production.
    #
    # Đã đo lại ngày 26/08/2026 trên đủ 29 câu golden dataset, chấm bằng
    # claude-sonnet-5: 17 đạt / 2 không đạt, trích nguồn đầy đủ ở mọi lượt có
    # khẳng định (eval/results/diem_*_batch3-sua.md). Luật "đổi model thì ĐO
    # TRƯỚC bằng `cli eval answer --doi-chieu`" vẫn nguyên giá trị cho lần sau.
    llm_model_answer: str = "gpt-5.6-luna"
    # Tầng rẻ: router (phân nhãn + giải tham chiếu) và sinh gợi ý câu hỏi tiếp
    # theo. Tài khoản chưa có quyền dùng thì đặt lại LLM_MODEL_FAST trong .env.
    llm_model_fast: str = "gpt-5.6-luna"
    llm_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    # 2048 chứ không phải 1024: câu "liệt kê các căn dưới 3 tỷ" trả 21 căn đã
    # ngốn ~950 token, sát trần cũ. Chạm trần thì câu trả lời đứt giữa chừng —
    # hỏng câm, không có lỗi nào báo ra.
    llm_max_tokens: int = Field(default=2048, gt=0)
    llm_timeout_s: float = Field(default=60.0, gt=0)

    # ---------- Orchestrator (nhà cung cấp thứ hai) ----------
    # Model đắt hơn hẳn nên CHỈ chạy ở nhánh leo thang, không nằm trên đường
    # đi chung. Xem `src/agents/leo_thang.py` cho điều kiện kích hoạt.
    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-sonnet-5"
    # `effort` là cần điều khiển chi phí chính của Sonnet 5: adaptive thinking
    # bật mặc định và token suy nghĩ tính theo GIÁ ĐẦU RA. Đừng tắt hẳn thinking
    # để tiết kiệm — tắt xong model gọi tool ít hẳn, đúng thứ orchestrator cần.
    orchestrator_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    orchestrator_max_tokens: int = Field(default=4096, gt=0)
    orchestrator_timeout_s: float = Field(default=120.0, gt=0)
    # Mặc định TẮT. Bật ở dev, đo, rồi mới tính chuyện production — với ngân
    # sách $5 thì đây là tính năng để đo đạc, chưa phải để bật cho lưu lượng thật.
    enable_orchestrator: bool = False
    # Trần cứng. 3 chứ không 5: mỗi vòng gửi lại toàn bộ lịch sử nên chi phí
    # tăng nhanh hơn tuyến tính theo số vòng.
    orchestrator_max_iterations: int = Field(default=3, ge=1, le=5)
    # Phanh chống tai nạn cho ngân sách $5. 0 = không giới hạn. Chạm trần thì
    # cổng leo thang tự đóng và khách vẫn nhận câu trả lời từ đường tất định.
    orchestrator_daily_budget_usd: float = Field(default=0.0, ge=0.0)
    # Cổng phân loại chính sách — chặn câu hỏi ngoài phạm vi / không an toàn
    # TRƯỚC khi trả lời. Chạy SONG SONG với tools+retrieve nên gần như không cộng
    # vào thời gian khách chờ. Xem `src/agents/chinh_sach.py`.
    #
    # Mặc định TẮT vì đây là cổng CHẶN: bật nhầm là từ chối khách thật. Bật ở dev,
    # đo tỷ lệ từ chối oan trên bộ eval, rồi mới tính chuyện production — khác hẳn
    # `che_do_leo_thang` vốn chỉ thêm bằng chứng nên chạy rộng không hại ai.
    enable_cong_chinh_sach: bool = False
    # Rỗng thì dùng `orchestrator_model`. Tách riêng để đổi được sang model rẻ
    # hơn mà không đụng nhánh leo thang — phân loại 4 nhãn không cần model mạnh
    # bằng việc chọn tool.
    cong_chinh_sach_model: str = ""
    # Khi nào orchestrator chạy:
    #   tat       — không bao giờ, đường tất định lo hết
    #   khi_thieu — chỉ khi một trong ba luật hẹp khớp
    #   moi_luot  — MỌI câu cần dữ liệu; orchestrator thành một tầng thật
    #
    # Mặc định `moi_luot`: bản đầu để `khi_thieu` và đo thật thì nó khớp 0/8 câu
    # điển hình — một tính năng không bao giờ chạy thì không khác gì không có.
    # Chạy rộng rồi siết theo số đo, đừng thiết kế hẹp sẵn rồi hy vọng nó vừa.
    che_do_leo_thang: Literal["tat", "khi_thieu", "moi_luot"] = "moi_luot"
    # Ba luật hẹp, chỉ có tác dụng khi `che_do_leo_thang="khi_thieu"`. Xem
    # `src/agents/leo_thang.py`. Bắt đầu chỉ bật R1 — nó bắt đúng nhánh hôm nay
    # đang trả "chưa đủ dữ liệu", tức chỗ chắc chắn không làm tệ đi thứ gì.
    leo_thang_r1: bool = True
    leo_thang_r2: bool = False
    leo_thang_r3: bool = False

    # ---------- Vector store ----------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "documents_chunks"
    # qdrant-client mặc định 5 giây — quá ngắn cho lần gọi đầu tới Qdrant Cloud
    # sau một lúc không dùng. Xem chú thích ở QdrantVectorStore.__init__.
    qdrant_timeout_s: float = Field(default=20.0, gt=0)
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

    # ---------- Chốt chặn của lõi AI ----------
    # Render khai service này là `type: web` nên nó có URL công khai. Khoá dùng
    # chung với API sản phẩm là thứ duy nhất ngăn người lạ gọi thẳng vào đây và
    # tiêu quota OpenAI của đội. Xem `src/api/bao_ve.py`.
    #
    # Rỗng: production CHẶN HẾT (cổng thất bại theo hướng mở thì không phải
    # cổng), môi trường khác cho qua kèm WARNING để `make run-ai` vẫn thử được.
    ai_core_api_key: str = ""
    # Phanh tay chi phí, đếm cho CẢ tiến trình chứ không theo IP — người gọi hợp
    # lệ duy nhất là API sản phẩm nên mọi request chung một IP. 0 = tắt.
    # Đặt cao hơn hẳn lưu lượng thật: nó để bắt lúc có gì đó chạy loạn, không
    # phải để chia phần cho người dùng (việc đó ở `app/core/han_muc.py`).
    ai_core_rate_limit_per_minute: int = Field(default=60, ge=0)

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

    @property
    def has_anthropic_key(self) -> bool:
        """Thiếu key Anthropic KHÔNG chặn khởi động — khác hẳn key OpenAI.

        Lý do: OpenAI nằm trên đường đi chung, thiếu nó là cả trợ lý ngừng hoạt
        động nên phải dừng sớm. Anthropic chỉ phục vụ nhánh leo thang; thiếu nó
        thì hệ thống vẫn trả lời đầy đủ bằng đường tất định, chỉ mất phần xử lý
        câu nhiều bước. Dừng cả app vì một tính năng phụ là đánh đổi sai.
        """
        return bool(self.anthropic_api_key) and not self.anthropic_api_key.startswith(("sk-your", "test"))


# Khoá mà biến môi trường của HĐH ghi đè lên `.env` sẽ gây lỗi khó chẩn đoán:
# request vẫn gửi đi, server vẫn trả 400 có nội dung hợp lý, không chỗ nào nói
# rằng đang dùng nhầm khoá.
_KHOA_DE_NHAM = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def canh_bao_env_ghi_de(duong_dan_env: str = ".env") -> list[str]:
    """Cảnh báo khi biến môi trường HĐH che mất giá trị khác trong `.env`.

    Vì sao cần: `pydantic-settings` ưu tiên biến môi trường HƠN file `.env` —
    đúng chuẩn và thường là điều mình muốn, nhưng nó biến một cấu hình sai thành
    lỗi câm. Ca thật đã tốn cả buổi chẩn đoán: máy có sẵn `ANTHROPIC_API_KEY`
    của một tài khoản khác, key đúng nằm trong `.env` không bao giờ được dùng,
    và API trả "credit balance is too low" — một thông điệp đúng về mặt kỹ thuật
    nhưng dẫn người đọc đi sai hướng hoàn toàn (đi nạp tiền thay vì đi xoá biến).

    Chỉ CẢNH BÁO chứ không đảo thứ tự ưu tiên: production nạp cấu hình qua biến
    môi trường là chuyện bình thường, đảo lại sẽ phá đúng cách deploy đang chạy.

    Trả về tên các khoá đang bị che, để test kiểm được mà không phải đọc log.
    """
    duong = Path(duong_dan_env)
    if not duong.exists():
        return []

    bi_che: list[str] = []
    for dong in duong.read_text(encoding="utf-8", errors="replace").splitlines():
        dong = dong.strip()
        if not dong or dong.startswith("#") or "=" not in dong:
            continue
        khoa, gia_tri = (phan.strip() for phan in dong.split("=", 1))
        if khoa not in _KHOA_DE_NHAM or not gia_tri:
            continue

        tu_moi_truong = os.environ.get(khoa)
        if tu_moi_truong and tu_moi_truong != gia_tri:
            bi_che.append(khoa)
            logger.warning(
                "%s trong biến môi trường ĐANG CHE giá trị khác trong .env — ứng dụng dùng "
                "bản của biến môi trường. Nếu không cố ý, xoá biến đó đi rồi chạy lại.",
                khoa,
            )
    return bi_che


@lru_cache
def get_settings() -> Settings:
    """Trả về Settings dạng singleton (cache theo process)."""
    return Settings()
