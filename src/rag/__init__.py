"""Module RAG — đường ĐỌC dữ liệu.

    câu hỏi → embed → search (lọc quyền) → rerank → grounding → prompt

Chủ sở hữu: phuc

Cấu trúc:
    contracts.py   RetrievalResult · Retriever · Reranker  (đóng băng)
    retriever.py   DefaultRetriever · EmptyRetriever
    rerankers.py   Passthrough · KeywordOverlap · CrossEncoder
    grounding.py   Dựng prompt có ngữ cảnh, ép LLM chỉ dựa trên tài liệu

Vì sao tách khỏi `src/data/`: data lo **đưa dữ liệu vào** store, rag lo **lấy ra
và dùng**. Trước đây hai việc này nằm lẫn trong `src/data/`, khiến không ai sở
hữu "RAG từ đầu đến cuối" — Phúc làm các mảnh rời, Huy sở hữu điểm nối ở
bootstrap, và 870 chunk nằm im nhiều ngày vì khoảng giữa không thuộc về ai.

Tầng agent chỉ import `Retriever` từ `contracts.py`; nó không biết Qdrant,
embedding model hay reranker nào đang chạy.
"""

from src.rag.contracts import Reranker, RetrievalResult, Retriever

__all__ = ["Reranker", "RetrievalResult", "Retriever"]
