"""Demo chạy thử nghiệm RAG Retrieval: Vector Search + Structured Filter.

Chạy lệnh:
    .venv\\Scripts\\python.exe scripts/demo_retrieval.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Thêm thư mục gốc dự án vào sys.path để import src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.contracts import Chunk, RetrievalFilter
from src.data.ingestion.embedders import FakeEmbedder
from src.data.retrieval.rerankers import PassthroughReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.memory_store import InMemoryVectorStore


async def run_demo() -> None:
    print("=" * 60)
    print("DEMO CHAY THU RAG RETRIEVAL (PRE-FILTER + VECTOR SEARCH)")
    print("=" * 60)

    # 1. Khởi tạo Embedder và Vector Store
    embedder = FakeEmbedder(dimension=32)
    store = InMemoryVectorStore()
    retriever = DefaultRetriever(embedder, store, PassthroughReranker())

    # 2. Tạo danh sách căn hộ mẫu
    sample_chunks = [
        Chunk(
            id="CAN-001",
            text="Can ho 2 phong ngu toa S1.01 thiet ke hien dai, ban cong huong Dong Nam mat me.",
            doc_id="DOC-BDS-01",
            doc_title="Bang hang Vinhomes Grand Park",
            metadata={
                "price": 3.5,  # tỷ VNĐ
                "area": 65.0,  # m²
                "num_bedrooms": 2,
                "building": "S1.01",
                "property_type": "2PN",
            },
        ),
        Chunk(
            id="CAN-002",
            text="Can ho 3 phong ngu goc toa S1.02 rong rai, view cong vien 36ha tuyet dep.",
            doc_id="DOC-BDS-01",
            doc_title="Bang hang Vinhomes Grand Park",
            metadata={
                "price": 5.2,
                "area": 92.0,
                "num_bedrooms": 3,
                "building": "S1.02",
                "property_type": "3PN",
            },
        ),
        Chunk(
            id="CAN-003",
            text="Can Studio toa S1.01 nho gon, full noi that cao cap, phu hop cho nguoi don than.",
            doc_id="DOC-BDS-01",
            doc_title="Bang hang Vinhomes Grand Park",
            metadata={
                "price": 2.1,
                "area": 32.0,
                "num_bedrooms": 1,
                "building": "S1.01",
                "property_type": "Studio",
            },
        ),
        Chunk(
            id="CAN-004",
            text="Can ho 2 phong ngu toa S1.02 noi that co ban chu dau tu, gia tot dau tu.",
            doc_id="DOC-BDS-01",
            doc_title="Bang hang Vinhomes Grand Park",
            metadata={
                "price": 3.8,
                "area": 68.0,
                "num_bedrooms": 2,
                "building": "S1.02",
                "property_type": "2PN",
            },
        ),
    ]

    # 3. Nạp dữ liệu vào Vector Store
    vectors = await embedder.embed_texts([c.text for c in sample_chunks])
    await store.upsert(sample_chunks, vectors)
    print(f"[+] Da nap thanh cong {len(sample_chunks)} can ho mau vao Vector Store.\n")

    # 4. Thực hiện thử nghiệm 1: Lọc khoảng giá [3.0 - 4.0 tỷ] & Số phòng = 2
    query = "Tim can ho chung cu 2 phong ngu dep"
    filters = RetrievalFilter(
        min_price=3.0,
        max_price=4.0,
        num_bedrooms=2,
    )

    print(f"[*] Cau hoi: '{query}'")
    print(f"[*] Bo loc cau truc (Filter First): Gia [3.0 - 4.0 ty], So phong = 2")
    print("-" * 60)

    result = await retriever.retrieve(query, filters=filters, top_k=5)

    if not result.chunks:
        print("[-] Khong tim thay can ho nao thoa man dieu kien.")
    else:
        print(f"[+] Tim thay {len(result.chunks)} can ho phu hop (Da rank theo Cosine Similarity):")
        for i, chunk in enumerate(result.chunks, 1):
            meta = chunk.metadata
            print(f"\n  [{i}] Ma can: {chunk.id} (Diem Cosine: {chunk.score:.4f})")
            print(f"      - Noi dung: {chunk.text}")
            print(f"      - Gia: {meta.get('price')} ty | Dien tich: {meta.get('area')}m2 | Toa: {meta.get('building')} | Loai: {meta.get('property_type')}")

    # 5. Thử nghiệm 2: Lọc Tòa S1.01 & Loại căn Studio
    print("\n" + "=" * 60)
    filters_studio = RetrievalFilter(building="S1.01", property_type="Studio")
    print("[*] Thu nghiem 2: Loc Toa S1.01 & Loai can Studio")
    print("-" * 60)

    result_studio = await retriever.retrieve("Can studio nho gon", filters=filters_studio, top_k=5)
    for i, chunk in enumerate(result_studio.chunks, 1):
        meta = chunk.metadata
        print(f"  [{i}] Ma can: {chunk.id} | Gia: {meta.get('price')} ty | Toa: {meta.get('building')}")
        print(f"      Noi dung: {chunk.text}")

    print("\n" + "=" * 60)
    print("[+] Hoan tat demo RAG Retrieval!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_demo())
