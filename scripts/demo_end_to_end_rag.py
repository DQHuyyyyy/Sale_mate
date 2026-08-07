"""Demo RAG End-to-End: Nhận câu hỏi -> Retrieve (Top-12) & Rerank (Top-3) -> Gọi OpenAI -> In câu trả lời + Nguồn ra console.

Chạy lệnh:
    .venv\\Scripts\\python.exe scripts/demo_end_to_end_rag.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Đảm bảo in ra được tiếng Việt trên console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thêm thư mục gốc dự án vào sys.path để import src
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.agents.nodes.generate import build_messages
from src.agents.state import initial_state
from src.core.config import get_settings
from src.core.exceptions import SalesMateError
from src.data.contracts import Chunk, RetrievalFilter
from src.data.ingestion.embedders import FakeEmbedder
from src.data.retrieval.rerankers import FakeCrossEncoderReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.memory_store import InMemoryVectorStore
from src.models.chat import ChatResponse, Citation
from src.services.llm import OpenAIProvider, ScriptedProvider


async def setup_demo_store() -> DefaultRetriever:
    """Khởi tạo Store dữ liệu RAG mẫu (Bảng hàng thật VOP + Chính sách bán hàng)."""
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    reranker = FakeCrossEncoderReranker()
    retriever = DefaultRetriever(embedder, store, reranker, top_k=12, top_n=3)

    sample_chunks = [
        Chunk(
            id="VOP398",
            text="Ma can: VOP398, Toa R103, Tang 27. Loai can: 1 PN, 1WC. Gia: 3,1 tỷ. Dien tich: 49m2. View bien ho biet thu. Noi that full xin.",
            doc_id="GOOGLE_SHEET_VOP",
            doc_title="Bảng hàng Vinhomes Ocean Park Real Data",
            metadata={
                "ma_can": "VOP398",
                "price": 3.1,
                "building": "R103",
                "doc_kind": "listing",
                "image_url": "https://img.salesmate.vn/vop/r103_2702.jpg",
            },
        ),
        Chunk(
            id="VOP639",
            text="Ma can: VOP639, Toa S2, Tang 21. Loai can: 2 PN, 1WC. Gia: 3.55 tỷ. Dien tich: 56m2. View bien ho biet thu thong thoáng.",
            doc_id="GOOGLE_SHEET_VOP",
            doc_title="Bảng hàng Vinhomes Ocean Park Real Data",
            metadata={
                "ma_can": "VOP639",
                "price": 3.55,
                "building": "S2",
                "doc_kind": "listing",
                "image_url": "https://img.salesmate.vn/vop/s2_2105.jpg",
            },
        ),
        Chunk(
            id="POL-001",
            text="Chinh sach Chiet khau Thanh toan som: Chiet khau truc tiep 8% vao hop dong khi thanh toan du 95% gia tri can ho trong 15 ngay.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Chiết khấu 8% Thanh toán sớm",
            metadata={"doc_kind": "policy", "title": "Chiết khấu 8% thanh toán sớm"},
        ),
        Chunk(
            id="POL-002",
            text="Chinh sach Ho tro Lai suat Ngan hang: Ngan hang ho tro vay 70% gia tri can ho, Lai suat 0% va an han no goc trong 24 thang.",
            doc_id="DOC-POL-02",
            doc_title="Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất",
            metadata={"doc_kind": "policy", "title": "Vay 70%, 0% lãi suất 24 tháng"},
        ),
    ]

    vectors = await embedder.embed_texts([c.text for c in sample_chunks])
    await store.upsert(sample_chunks, vectors)
    return retriever


async def process_question(query: str, retriever: DefaultRetriever, llm: Any) -> None:
    print("\n" + "=" * 80)
    print(f"❓ CÂU HỎI: \"{query}\"")
    print("=" * 80)

    # 1. RETRIEVE & RERANK (Lấy Top-12 -> Rerank Top-3)
    ret_result = await retriever.retrieve(query, top_k=12, top_n=3)
    context_text = ret_result.as_context()

    print("\n🔍 1. KẾT QUẢ RETRIEVAL & CROSS-ENCODER RERANK (TOP-3 CHUNKS):")
    for idx, chunk in enumerate(ret_result.chunks, 1):
        print(f"   [{idx}] ID: {chunk.id} | Nguồn: {chunk.doc_title} | Score: {chunk.score}")

    # 2. GHÉP CONTEXT VÀO PROMPT & GỌI OPENAI
    state = initial_state(query, "demo_session_cli")
    state["context"] = context_text
    messages = build_messages(state)

    print("\n🤖 2. GỌI OPENAI / LLM STREAMING CÂU TRẢ LỜI REAL-TIME:")
    print("   \"", end="", flush=True)

    streamed_tokens: list[str] = []
    try:
        async for token in llm.stream(messages):
            print(token, end="", flush=True)
            streamed_tokens.append(token)
    except SalesMateError as exc:
        print(f"\n⚠️ [{exc.__class__.__name__}]: {exc.message}")
        print("💡 Chuyển sang ScriptedProvider giả lập để hoàn tất demo:")
        fallback_reply = (
            "Căn hộ mã [VOP398] tại tòa R103 có giá bán gốc là 3,1 tỷ [Bảng hàng Vinhomes Ocean Park Real Data]. "
            "Căn hộ này có view biển hồ biệt thự trực diện rất đẹp. "
            "Hiện căn hộ đang được áp dụng [Chính sách Chiết khấu 8% Thanh toán sớm] (giá sau chiết khấu còn khoảng 2,852 tỷ) "
            "hoặc [Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất] trong 24 tháng."
        )
        mock_llm = ScriptedProvider(fallback_reply, delay_s=0.02)
        streamed_tokens = []
        async for token in mock_llm.stream(messages):
            print(token, end="", flush=True)
            streamed_tokens.append(token)

    print("\"\n")

    full_answer = "".join(streamed_tokens).strip()

    # 3. TÁCH NGUỒN CITATIONS VÀ IN OUT CONSOLE
    citations = [
        Citation(
            doc_id=c.doc_id,
            title=c.doc_title or c.doc_id,
            version=c.version,
            page=c.page,
            section=c.section,
            kind="doc",
        )
        for c in ret_result.chunks
    ]

    response = ChatResponse(
        message=full_answer,
        session_id=state["session_id"],
        citations=citations,
    )

    print("=" * 80)
    print("📌 3. KẾT QUẢ CUỐI CÙNG (CÂU TRẢ LỜI & NGUỒN TÁCH BIỆT):")
    print("=" * 80)
    print(f"📝 [ANSWER]:\n{response.answer}\n")
    print(f"📚 [SOURCES / NGUỒN TRÍCH DẪN ({len(response.sources)} nguồn)]:")
    for idx, src in enumerate(response.sources, 1):
        print(f"   {idx}. {src.title} (doc_id: {src.doc_id})")

    print("\n📦 [JSON HEADLESS OUTPUT CHO FRONTEND]:")
    print(json.dumps(response.to_formatted_dict(), ensure_ascii=False, indent=2))
    print("=" * 80)


async def main() -> None:
    print("=" * 80)
    print("🚀 DEMO RAG END-TO-END: RETRIEVE -> RERANK -> OPENAI -> ANSWER + SOURCES")
    print("=" * 80)

    retriever = await setup_demo_store()

    # Cấu hình LLM Provider
    settings = get_settings()
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")

    if api_key and not api_key.startswith("sk-placeholder"):
        print("🔑 Đã phát hiện OpenAI API Key. Khởi tạo OpenAIProvider (gpt-4o-mini).")
        llm = OpenAIProvider(api_key=api_key, default_model="gpt-4o-mini")
    else:
        print("💡 Chưa cấu hình OPENAI_API_KEY. Khởi tạo ScriptedProvider giả lập streaming.")
        llm = ScriptedProvider(
            "Căn hộ mã [VOP398] tại tòa R103 có giá bán gốc là 3,1 tỷ [Bảng hàng Vinhomes Ocean Park Real Data]. "
            "Căn hộ được hưởng [Chính sách Chiết khấu 8% Thanh toán sớm] (giá sau chiết khấu là 2,852 tỷ) "
            "hoặc [Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất] trong 24 tháng.",
            delay_s=0.02,
        )

    # Chạy câu hỏi mẫu
    default_query = "Căn VOP398 giá bao nhiêu và có những chính sách ưu đãi nào?"
    await process_question(default_query, retriever, llm)


if __name__ == "__main__":
    asyncio.run(main())
