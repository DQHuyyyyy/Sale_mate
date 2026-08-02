"""Chat thử với agent, RAG bật sẵn, đọc thẳng từ Qdrant thật đã ingest sẵn.

KHÔNG đụng src/bootstrap.py (file chung của cả team) — script này tự dựng một
agent riêng, độc lập, chỉ để test cục bộ trên máy bạn. Muốn bật RAG thật cho
cả app thì phải sửa bootstrap.py, việc đó cần huy/viet đồng ý.

Chạy (cần đã `make infra` + chạy scripts/ingest_inventory.py và
scripts/ingest_batdongsan.py trước để có dữ liệu trong Qdrant):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/chat_demo_rag.py
"""

from __future__ import annotations

import asyncio

from src.agents.graph import build_graph, build_nodes
from src.agents.service import LangGraphAgentService
from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.qdrant_store import QdrantVectorStore
from src.models.chat import ChatRequest
from src.services.llm import OpenAIProvider, ScriptedProvider

logger = get_logger(__name__)

DEMO_QUESTIONS = [
    "Cho tôi thông tin căn hộ 3 phòng ngủ ở Vinhomes Ocean Park",
    "Có biệt thự song lập nào không, giá bao nhiêu?",
    "Thủ tục sang tên sổ đỏ gồm những gì?",  # câu KHÔNG có trong dữ liệu -> phải từ chối
]


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    # ---- Đọc thẳng Qdrant thật — dữ liệu đã ingest sẵn bằng scripts/ingest_*.py ----
    embedder = OpenAIEmbedder(settings.openai_api_key) if settings.has_openai_key else FakeEmbedder(dimension=64)
    store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection)
    count = await store.count()
    logger.info("Qdrant collection '%s' hiện có %d chunk", settings.qdrant_collection, count)

    # ---- Dựng agent, RAG bật cứng cho script này (không đụng bootstrap.py) ----
    llm = OpenAIProvider(settings.openai_api_key) if settings.has_openai_key else ScriptedProvider()
    retriever = DefaultRetriever(embedder, store, KeywordOverlapReranker())
    nodes = build_nodes(llm, retriever, settings)
    graph = build_graph(nodes)
    agent = LangGraphAgentService(graph, llm, settings, nodes=nodes, enable_rag=True)

    if not settings.has_openai_key:
        print("\n*** Chưa có OPENAI_API_KEY hợp lệ -> dùng LLM giả lập (ScriptedProvider). ***")
        print("*** Router/retrieve vẫn chạy thật, nhưng câu trả lời cuối là câu mẫu cố định. ***\n")

    for question in DEMO_QUESTIONS:
        request = ChatRequest(message=question)
        response = await agent.answer(request)
        print(f"\n=== Hỏi: {question} ===")
        print(f"Trả lời: {response.message}")
        print(f"Nguồn ({len(response.citations)}):")
        for citation in response.citations:
            print(f"  - {citation.title} | {citation.doc_id}")


if __name__ == "__main__":
    asyncio.run(main())
