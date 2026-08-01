"""Wiring — nơi DUY NHẤT gắn Protocol với implementation cụ thể.

Đọc file này là biết toàn bộ hệ thống đang chạy bằng gì. Đổi Qdrant ↔ in-memory,
OpenAI ↔ giả lập, mock portal ↔ SQL đều sửa ở đây, không đụng code gọi.

src/core/ không import file này (tránh vòng lặp); main.py gọi configure().
"""

from __future__ import annotations

from src.agents.contracts import AgentService, LLMProvider
from src.agents.graph import build_graph, build_nodes
from src.agents.service import LangGraphAgentService
from src.core.config import Settings, get_settings
from src.core.container import Container, container
from src.core.logging import get_logger
from src.data.contracts import Embedder, Retriever, VectorStore
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever, EmptyRetriever
from src.data.stores.memory_store import InMemoryVectorStore
from src.services.llm import OpenAIProvider, ScriptedProvider
from src.services.portal import InMemoryPortalRepository, PortalRepository

logger = get_logger(__name__)

# Bật khi module Data đã nạp tài liệu thật vào vector store.
# Đang tắt: trợ lý trả lời trực tiếp bằng LLM, chưa tra tài liệu.
ENABLE_RAG = False


def configure(target: Container | None = None, settings: Settings | None = None) -> Container:
    """Đăng ký toàn bộ dịch vụ vào container."""
    box = target or container
    cfg = settings or get_settings()

    box.register_instance(Settings, cfg)

    # ---------- LLM ----------
    def make_llm() -> LLMProvider:
        if not cfg.has_openai_key:
            logger.warning("Chưa có OPENAI_API_KEY hợp lệ — dùng LLM giả lập.")
            return ScriptedProvider()
        return OpenAIProvider(
            cfg.openai_api_key,
            default_model=cfg.llm_model_fast,
            timeout_s=cfg.llm_timeout_s,
        )

    box.register(LLMProvider, make_llm)

    # ---------- Data ----------
    def make_embedder() -> Embedder:
        if not cfg.has_openai_key:
            return FakeEmbedder()
        return OpenAIEmbedder(
            cfg.openai_api_key,
            model=cfg.embedding_model,
            dimension=cfg.embedding_dim,
        )

    box.register(Embedder, make_embedder)
    # Mặc định in-memory: dev/test chạy được không cần Docker.
    # Đổi sang Qdrant: trả về QdrantVectorStore(cfg.qdrant_url, cfg.qdrant_collection).
    box.register(VectorStore, InMemoryVectorStore)

    def make_retriever() -> Retriever:
        if not ENABLE_RAG:
            return EmptyRetriever()
        return DefaultRetriever(
            box.resolve(Embedder),
            box.resolve(VectorStore),
            KeywordOverlapReranker(),
            top_k=cfg.retrieval_top_k,
            top_n=cfg.rerank_top_n,
        )

    box.register(Retriever, make_retriever)

    # ---------- Portal ----------
    box.register(PortalRepository, InMemoryPortalRepository)

    # ---------- Agent ----------
    def make_agent() -> AgentService:
        llm = box.resolve(LLMProvider)
        nodes = build_nodes(llm, box.resolve(Retriever), cfg)
        return LangGraphAgentService(
            build_graph(nodes),
            llm,
            cfg,
            nodes=nodes,
            enable_rag=ENABLE_RAG,
        )

    box.register(AgentService, make_agent)

    logger.info(
        "Đã cấu hình dịch vụ",
        extra={"context": {"rag": ENABLE_RAG, "llm_real": cfg.has_openai_key}},
    )
    return box
