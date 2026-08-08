"""Đo chất lượng lõi AI trên bộ câu hỏi vàng.

Nguyên tắc: **mọi số đo phải chạy trên dịch vụ thật.** Repo này từng có một bộ
eval chạy hoàn toàn bằng FakeEmbedder + InMemoryVectorStore + ScriptedProvider,
báo cáo ra "độ trễ 0,22ms" và "hit rate 100%" — những con số bất khả thi, và
đã bị gỡ bỏ. Đừng lặp lại.

Chạy:
    python -m src.cli eval retrieval
"""

from src.eval.retrieval import RetrievalEvalSummary, run_retrieval_eval

__all__ = ["RetrievalEvalSummary", "run_retrieval_eval"]
