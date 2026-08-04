"""Eval retrieval — mục 10 Data Handling: bộ câu hỏi kiểm thử (golden dataset).

Chạy Retriever THẬT (embed câu hỏi → search Qdrant thật → rerank) trên từng
câu trong eval/golden_dataset.json, đo hit@top_n (tài liệu mong đợi có nằm
trong kết quả trả về không) và coverage. Không gọi LLM, không đo "response
accuracy" của agent (thuộc phạm vi module agents) — đây chỉ đo tầng data.

Dùng filter visibility=["public","internal"] (không phải mặc định chỉ public)
— eval này đo NĂNG LỰC RETRIEVAL của toàn bộ dữ liệu đã ingest, tách biệt khỏi
bài toán phân quyền (đã có test end-to-end riêng ở mục 7 Data Handling). Nếu
dùng filter mặc định, câu hỏi về tồn kho (visibility=internal) sẽ luôn "miss"
dù dữ liệu đúng — đó là false negative do quyền hạn, không phải lỗi retrieval.

Chạy (cần `make infra` bật Qdrant + đã ingest dữ liệu trước):
    PYTHONUTF8=1 PYTHONPATH=. .venv/Scripts/python.exe scripts/eval_retrieval.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger, setup_logging
from src.data.contracts import RetrievalFilter
from src.data.ingestion.embedders import FakeEmbedder, OpenAIEmbedder
from src.data.retrieval.rerankers import KeywordOverlapReranker
from src.data.retrieval.retriever import DefaultRetriever
from src.data.stores.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "eval" / "golden_dataset.json"
REPORT_PATH = Path(__file__).resolve().parents[1] / "eval" / "results" / "retrieval_eval.json"


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()

    embedder = OpenAIEmbedder(settings.openai_api_key) if settings.has_openai_key else FakeEmbedder(dimension=64)
    store = QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, api_key=settings.qdrant_api_key)
    retriever = DefaultRetriever(embedder, store, KeywordOverlapReranker())

    golden_set = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    results = []
    hits = 0
    positive_cases = 0

    eval_filter = RetrievalFilter(visibility=["public", "internal"])
    for case in golden_set:
        result = await retriever.retrieve(case["question"], top_k=10, top_n=5, filters=eval_filter)
        retrieved_ids = [chunk.doc_id for chunk in result.chunks]
        expected = case["expected_doc_id"]

        if expected is None:
            passed = result.coverage < settings.coverage_threshold
        else:
            positive_cases += 1
            passed = expected in retrieved_ids
            hits += int(passed)

        results.append(
            {
                "question": case["question"],
                "expected_doc_id": expected,
                "retrieved_doc_ids": retrieved_ids,
                "coverage": round(result.coverage, 3),
                "passed": passed,
            }
        )
        logger.info("[%s] %s -> coverage=%.2f", "OK" if passed else "MISS", case["question"], result.coverage)

    accuracy = hits / positive_cases if positive_cases else 0.0
    summary = {
        "total_cases": len(golden_set),
        "positive_cases": positive_cases,
        "hit_at_5_accuracy": round(accuracy, 3),
        "coverage_threshold": settings.coverage_threshold,
        "embedder": "OpenAIEmbedder" if settings.has_openai_key else "FakeEmbedder",
        "results": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Hit@5 = %d/%d (%.0f%%) — chi tiết: %s", hits, positive_cases, accuracy * 100, REPORT_PATH)


if __name__ == "__main__":
    asyncio.run(main())
