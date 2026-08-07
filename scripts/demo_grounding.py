"""Script demo chạy thử nghiệm Prompt Engineering, Ép Grounding & Chống Hallucination.

Chạy lệnh:
    .venv\\Scripts\\python.exe scripts/demo_grounding.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Đảm bảo in ra được tiếng Việt trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm thư mục gốc dự án vào sys.path để import src
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.agents.graph import build_graph, build_nodes
from src.agents.nodes.generate import GenerateNode, build_messages
from src.agents.nodes.guardrail import GuardrailNode
from src.agents.prompts import system_prompt
from src.agents.state import initial_state
from src.core.config import Settings
from src.data.contracts import Chunk, RetrievalFilter
from src.data.ingestion.embedders import FakeEmbedder
from src.data.retrieval.rerankers import FakeCrossEncoderReranker, PassthroughReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.memory_store import InMemoryVectorStore
from src.services.llm import ScriptedProvider


async def run_grounding_demo() -> None:
    print("=" * 70)
    print("🚀 DEMO TEST PROMPT ENGINEERING, GROUNDING & CHỐNG HALLUCINATION")
    print("=" * 70)

    # 1. Khởi tạo dữ liệu RAG mẫu & Cross-Encoder Reranker
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    reranker = FakeCrossEncoderReranker()
    retriever = DefaultRetriever(embedder, store, reranker, top_k=12, top_n=3)

    sample_chunks = [
        Chunk(
            id="VOP398",
            text="Ma can: VOP398, Toa R103, Tang 27. Loai can: 1 PN, 1WC. Gia: 3,1 tỷ. View bien ho biet thu. Noi that full xin.",
            doc_id="DOC-BDS-01",
            doc_title="Bảng hàng Vinhomes Ocean Park",
            metadata={"ma_can": "VOP398", "price": 3.1, "building": "R103", "doc_kind": "listing"},
        ),
        Chunk(
            id="POL-001",
            text="Chinh sach Chiet khau Thanh toan som: Chiet khau truc tiep 8% vao hop dong khi thanh toan du 95% gia tri can ho trong 15 ngay.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Chiết khấu 8%",
            metadata={"doc_kind": "policy", "title": "Chiết khấu 8% thanh toán sớm"},
        ),
    ]

    vectors = await embedder.embed_texts([c.text for c in sample_chunks])
    await store.upsert(sample_chunks, vectors)

    # 2. Tạo LLM Provider giả lập có trích dẫn nguồn
    grounded_reply = (
        "Căn hộ mã [VOP398] tại tòa R103 có giá bán là 3,1 tỷ [Bảng hàng Vinhomes Ocean Park]. "
        "Căn này được hưởng [Chính sách Chiết khấu 8%] khi thanh toán sớm 95% trong 15 ngày."
    )
    scripted_llm = ScriptedProvider(grounded_reply, delay_s=0)
    settings = Settings(app_env="test", openai_api_key="", coverage_threshold=0.35)

    nodes = build_nodes(scripted_llm, retriever, settings)
    graph = build_graph(nodes)

    # --------------------------------------------------------------------------
    # THỬ NGHIỆM A: Hỏi câu CÓ DỮ LIỆU trong RAG -> Ép Grounding + Trích dẫn nguồn
    # --------------------------------------------------------------------------
    print("\n" + "*" * 70)
    print("THỬ NGHIỆM A: Hỏi câu CÓ TRONG DỮ LIỆU RAG")
    print("*" * 70)
    q_valid = "Căn VOP398 giá bao nhiêu và có chiết khấu gì?"
    print(f"👉 Câu hỏi: '{q_valid}'")

    state_valid = initial_state(q_valid, "sess_1")
    result_valid = await graph.ainvoke(state_valid)

    print("\n🤖 AI Agent trả lời (Có trích dẫn nguồn [Mã căn] / [Tên tài liệu]):")
    print(f"   \"{result_valid['answer']}\"")
    if result_valid.get("citations"):
        print("📌 Nguồn trích dẫn đính kèm:")
        for cit in result_valid["citations"]:
            print(f"   - Document ID: {cit.doc_id} ({cit.title})")

    # --------------------------------------------------------------------------
    # THỬ NGHIỆM B: Hỏi câu KHÔNG CÓ TRONG DỮ LIỆU -> Chống Hallucination & Từ chối
    # --------------------------------------------------------------------------
    print("\n" + "*" * 70)
    print("THỬ NGHIỆM B: Hỏi câu KHÔNG CÓ TRONG DỮ LIỆU (Test Chống Bịa Thông Tin)")
    print("*" * 70)
    q_invalid = "Giá biệt thự Vinhomes Hải Phòng mã VOP9999 bao nhiêu tiền?"
    print(f"👉 Câu hỏi: '{q_invalid}'")

    empty_retriever = DefaultRetriever(embedder, InMemoryVectorStore(), PassthroughReranker())
    nodes_empty = build_nodes(scripted_llm, empty_retriever, settings)
    graph_empty = build_graph(nodes_empty)

    state_invalid = initial_state(q_invalid, "sess_2")
    result_invalid = await graph_empty.ainvoke(state_invalid)

    print("\n🛡️ AI Agent phản hồi (Chống Hallucination - Từ chối khi không có dữ liệu):")
    print(f"   \"{result_invalid['answer']}\"")

    print("\n" + "=" * 70)
    print("🎉 HOÀN TẤT TEST PROMPT ENGINEERING & GROUNDING!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_grounding_demo())
