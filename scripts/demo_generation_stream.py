"""Script demo chạy Generation (gọi OpenAI / LLM Stream + Rerank Top-3 Context + Tách riêng answer và sources[]).

Chạy lệnh:
    .venv\\Scripts\\python.exe scripts/demo_generation_stream.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

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


async def run_generation_stream_demo() -> None:
    print("=" * 75)
    print("🚀 DEMO GENERATION: GỌI OPENAI / LLM STREAM + CROSS-ENCODER + TÁCH ANSWER & SOURCES[]")
    print("=" * 75)

    # 1. Nạp dữ liệu RAG mẫu (Căn hộ & Chính sách)
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    reranker = FakeCrossEncoderReranker()
    retriever = DefaultRetriever(embedder, store, reranker, top_k=12, top_n=3)

    sample_chunks = [
        Chunk(
            id="VOP398",
            text="Ma can: VOP398, Toa R103, Tang 27. Loai can: 1 PN, 1WC. Gia: 3,1 tỷ. View bien ho biet thu. Noi that full xin.",
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
            id="POL-001",
            text="Chinh sach Chiet khau Thanh toan som: Chiet khau truc tiep 8% vao hop dong khi thanh toan du 95% gia tri can ho trong 15 ngay.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Chiết khấu 8% Thanh toán sớm",
            metadata={"doc_kind": "policy", "title": "Chiết khấu 8% thanh toán sớm"},
        ),
        Chunk(
            id="POL-002",
            text="Chinh sach Ho tro Lai suat Ngan hang: Ngan hang ho tro vay 70% gia tri can ho, Lai suat 0% va an han no goc trong 24 thang.",
            doc_id="DOC-POL-01",
            doc_title="Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất",
            metadata={"doc_kind": "policy", "title": "Vay 70%, 0% lãi suất 24 tháng"},
        ),
    ]

    vectors = await embedder.embed_texts([c.text for c in sample_chunks])
    await store.upsert(sample_chunks, vectors)

    # 2. Khởi tạo LLM Provider (Ưu tiên OpenAI nếu có API Key, nếu không dùng ScriptedProvider)
    settings = get_settings()
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")

    if api_key and not api_key.startswith("sk-placeholder"):
        print("🔑 Đã phát hiện OpenAI API Key. Sử dụng OpenAIProvider (gpt-4o-mini).")
        llm = OpenAIProvider(api_key=api_key, default_model="gpt-4o-mini")
    else:
        print("💡 Chưa cấu hình OPENAI_API_KEY. Sử dụng ScriptedProvider giả lập streaming.")
        reply_mock = (
            "Căn hộ mã [VOP398] tại tòa R103 có giá bán là 3,1 tỷ [Bảng hàng Vinhomes Ocean Park Real Data]. "
            "Căn hộ này có view biển hồ biệt thự trực diện rất đẹp. "
            "Hiện căn hộ được áp dụng [Chính sách Chiết khấu 8% Thanh toán sớm] (giá còn khoảng 2,852 tỷ) "
            "hoặc [Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất] trong 24 tháng."
        )
        llm = ScriptedProvider(reply_mock, delay_s=0.03)

    # 3. Thực hiện Truy hồi & Cross-Encoder Reranking
    query = "Căn VOP398 giá bao nhiêu và có những chính sách ưu đãi nào?"
    print(f"\n👉 Câu hỏi: '{query}'")

    res = await retriever.retrieve(query, top_k=12, top_n=3)
    context_text = res.as_context()

    print("\n" + "-" * 75)
    print("📋 Context đã qua Cross-Encoder Rerank (Top-3) ghép vào Prompt:")
    print(context_text)
    print("-" * 75)

    # 4. Xử lý Streaming Response (Token-by-Token)
    state = initial_state(query, "demo_session_101")
    state["context"] = context_text
    messages = build_messages(state)

    print("\n⚡ [STREAMING START] AI đang sinh câu trả lời real-time:")
    print("   \"", end="", flush=True)

    streamed_tokens: list[str] = []
    try:
        async for token in llm.stream(messages):
            print(token, end="", flush=True)
            streamed_tokens.append(token)
    except SalesMateError as exc:
        print(f"\n⚠️ [{exc.__class__.__name__}]: {exc.message}")
        print("💡 Chuyển sang ScriptedProvider giả lập để hoàn tất demo:")
        mock_llm = ScriptedProvider(
            "Căn hộ mã [VOP398] tại tòa R103 có giá gốc 3,1 tỷ [Bảng hàng Vinhomes Ocean Park Real Data]. "
            "Căn hộ này hưởng [Chính sách Chiết khấu 8% Thanh toán sớm] (giá sau chiết khấu là 2,852 tỷ) "
            "hoặc [Chính sách Hỗ trợ Vay Ngân hàng 0% Lãi suất] trong 24 tháng.",
            delay_s=0.02,
        )
        streamed_tokens = []
        async for token in mock_llm.stream(messages):
            print(token, end="", flush=True)
            streamed_tokens.append(token)

    print("\"\n⚡ [STREAMING DONE]\n")

    full_answer = "".join(streamed_tokens).strip()

    # 5. Format Output TÁCH RIÊNG answer và sources[] cho FE
    citations = [
        Citation(
            doc_id=c.doc_id,
            title=c.doc_title or c.doc_id,
            version=c.version,
            page=c.page,
            section=c.section,
            kind="doc",
        )
        for c in res.chunks
    ]

    response = ChatResponse(
        message=full_answer,
        session_id=state["session_id"],
        citations=citations,
    )

    print("=" * 75)
    print("📦 FORMAT OUTPUT TÁCH RIÊNG ANSWER VÀ SOURCES[] (JSON Cho Frontend):")
    print("=" * 75)
    print(json.dumps(response.to_formatted_dict(), ensure_ascii=False, indent=2))
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_generation_stream_demo())
