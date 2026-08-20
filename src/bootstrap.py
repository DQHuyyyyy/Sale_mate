"""Wiring — nơi DUY NHẤT gắn Protocol với implementation cụ thể.

Đọc file này là biết toàn bộ lõi AI đang chạy bằng gì. Đổi Qdrant ↔ in-memory,
OpenAI ↔ giả lập đều sửa ở đây, không đụng code gọi.

src/core/ không import file này (tránh vòng lặp); main.py gọi configure().

Mọi lựa chọn dưới đây đều lấy từ Settings chứ không hardcode — nhờ vậy đổi hành
vi bằng biến môi trường, không phải sửa code rồi commit.
"""

from __future__ import annotations

from src.agents.contracts import AgentService, LLMProvider, ToolCallingProvider
from src.agents.graph import build_graph, build_nodes
from src.agents.service import LangGraphAgentService
from src.core.config import Settings, canh_bao_env_ghi_de, get_settings
from src.core.container import Container, container
from src.core.exceptions import ConfigurationError
from src.core.logging import get_logger
from src.data.contracts import Embedder, VectorStore
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.stores.memory_store import InMemoryVectorStore
from src.data.stores.qdrant_store import QdrantVectorStore
from src.rag.contracts import Reranker, Retriever
from src.rag.rerankers import (
    CrossEncoderReranker,
    KeywordOverlapReranker,
    PassthroughReranker,
)
from src.rag.retriever import DefaultRetriever, EmptyRetriever
from src.services.llm import OpenAIProvider, ScriptedProvider, ScriptedToolCallingProvider

logger = get_logger(__name__)


def configure(target: Container | None = None, settings: Settings | None = None) -> Container:
    """Đăng ký toàn bộ dịch vụ vào container."""
    box = target or container
    cfg = settings or get_settings()

    box.register_instance(Settings, cfg)

    # Chạy SỚM, trước mọi lần gọi model: biến môi trường che mất khoá trong
    # `.env` là lỗi câm, phải hiện thành một dòng WARNING lúc khởi động.
    canh_bao_env_ghi_de()

    # Đồ giả lập CHỈ được dùng trong môi trường test. Ở dev và production, thiếu
    # khoá là dừng ngay — thà không chạy còn hơn phục vụ nội dung bịa ra.
    #
    # Trước đây thiếu OPENAI_API_KEY thì hệ thống âm thầm rơi về ScriptedProvider
    # (trả câu trả lời soạn sẵn) và FakeEmbedder (vector 64 chiều, không khớp
    # collection 1536 chiều). Người dùng nhận nội dung giả mà tưởng là thật, và
    # truy hồi hỏng theo kiểu khó chẩn đoán.
    if not cfg.has_openai_key and not cfg.is_test:
        raise ConfigurationError(
            "Thiếu OPENAI_API_KEY hợp lệ. Lõi AI không khởi động khi không có khoá thật — "
            "hệ thống chỉ trả lời dựa trên tài liệu, không dùng dữ liệu giả lập. "
            "Điền OPENAI_API_KEY vào .env rồi chạy lại."
        )

    # ---------- LLM ----------
    def make_llm() -> LLMProvider:
        if not cfg.has_openai_key:
            return ScriptedProvider()  # chỉ tới được ở APP_ENV=test
        return OpenAIProvider(
            cfg.openai_api_key,
            default_model=cfg.llm_model_fast,
            timeout_s=cfg.llm_timeout_s,
        )

    box.register(LLMProvider, make_llm)

    # ---------- Tool calling (orchestrator) ----------
    def make_tool_provider() -> ToolCallingProvider:
        """Thiếu key hoặc thiếu SDK Anthropic KHÔNG chặn khởi động.

        Khác hẳn `LLMProvider` ở trên: chỗ đó nằm trên đường đi chung nên thiếu
        key là trợ lý câm, phải dừng sớm. Orchestrator chỉ phục vụ nhánh leo
        thang; hỏng thì cổng tự đóng và mọi câu vẫn được trả lời bằng đường tất
        định.

        Bọc try/except quanh cả việc DỰNG provider chứ không chỉ việc gọi nó:
        `AnthropicToolProvider.__init__` dựng client ngay, và thiếu gói
        `anthropic` sẽ ném ngay tại đây. Không bắt thì lỗi lan lên
        `make_agent` → `AgentService` không resolve được → mọi request trả 502,
        tức một tính năng phụ chưa bật làm chết cả trợ lý.
        """
        if not cfg.enable_orchestrator:
            return ScriptedToolCallingProvider()
        if not cfg.has_anthropic_key:
            logger.warning("ENABLE_ORCHESTRATOR bật nhưng thiếu ANTHROPIC_API_KEY — nhánh leo thang tắt")
            return ScriptedToolCallingProvider()

        try:
            from src.services.anthropic_llm import AnthropicToolProvider

            return AnthropicToolProvider(
                cfg.anthropic_api_key,
                default_model=cfg.orchestrator_model,
                effort=cfg.orchestrator_effort,
                max_tokens=cfg.orchestrator_max_tokens,
                timeout_s=cfg.orchestrator_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 - hỏng ở đây không được làm sập app
            logger.warning("Không dựng được orchestrator Anthropic, nhánh leo thang tắt: %s", exc)
            return ScriptedToolCallingProvider()

    box.register(ToolCallingProvider, make_tool_provider)

    # ---------- Embedder ----------
    def make_embedder() -> Embedder:
        if not cfg.has_openai_key:
            return FakeEmbedder()  # chỉ tới được ở APP_ENV=test
        return OpenAIEmbedder(
            cfg.openai_api_key,
            model=cfg.embedding_model,
            dimension=cfg.embedding_dim,
        )

    box.register(Embedder, make_embedder)

    # ---------- Vector store ----------
    def make_vector_store() -> VectorStore:
        # Test luôn chạy trong bộ nhớ: không test nào được gọi Qdrant thật.
        if not cfg.use_real_vector_store:
            return InMemoryVectorStore()
        return QdrantVectorStore(
            cfg.qdrant_url,
            cfg.qdrant_collection,
            api_key=cfg.qdrant_api_key,
            timeout=cfg.qdrant_timeout_s,
        )

    box.register(VectorStore, make_vector_store)

    # ---------- Reranker ----------
    def make_reranker() -> Reranker:
        if cfg.reranker == "cross_encoder":
            return CrossEncoderReranker()
        if cfg.reranker == "passthrough":
            return PassthroughReranker()
        return KeywordOverlapReranker()

    box.register(Reranker, make_reranker)

    # ---------- Retriever ----------
    def make_retriever() -> Retriever:
        if not cfg.enable_rag:
            logger.warning("ENABLE_RAG tắt — trợ lý sẽ luôn trả lời 'chưa đủ dữ liệu'.")
            return EmptyRetriever()
        return DefaultRetriever(
            box.resolve(Embedder),
            box.resolve(VectorStore),
            box.resolve(Reranker),
            top_k=cfg.retrieval_top_k,
            top_n=cfg.rerank_top_n,
        )

    box.register(Retriever, make_retriever)

    # ---------- Agent ----------
    def make_agent() -> AgentService:
        llm = box.resolve(LLMProvider)
        nodes = build_nodes(llm, box.resolve(Retriever), cfg, box.resolve(ToolCallingProvider))
        return LangGraphAgentService(
            build_graph(nodes),
            llm,
            cfg,
            nodes=nodes,
            enable_rag=cfg.enable_rag,
        )

    box.register(AgentService, make_agent)

    logger.info(
        "Đã cấu hình lõi AI",
        extra={
            "context": {
                "rag": cfg.enable_rag,
                "vector_store": "qdrant" if cfg.use_real_vector_store else "memory",
                "qdrant_cloud": cfg.uses_qdrant_cloud,
                "reranker": cfg.reranker,
                "llm_real": cfg.has_openai_key,
                "orchestrator": cfg.orchestrator_model if cfg.has_anthropic_key else "tắt",
            }
        },
    )
    return box
