"""Đo năng lực truy hồi trên bộ câu hỏi vàng.

Chạy Retriever THẬT (embed câu hỏi → search Qdrant → rerank) trên từng câu
trong `eval/golden_dataset.json`, đo hit@n và coverage.

Không gọi LLM, không đo chất lượng câu trả lời — đây chỉ đo tầng truy hồi. Nếu
tầng này sai thì mọi thứ phía sau đều sai, nên đo nó trước.

Dùng filter `visibility=["public","internal"]` chứ không phải mặc định chỉ
`public`: eval này đo NĂNG LỰC TRUY HỒI trên toàn bộ dữ liệu, tách khỏi bài
toán phân quyền (đã có test riêng). Nếu lọc mặc định thì câu hỏi về tồn kho —
vốn là `internal` — sẽ luôn trượt dù dữ liệu đúng, tức là báo sai vì lý do
quyền hạn chứ không phải vì truy hồi kém.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from src.bootstrap import configure
from src.core.config import Settings
from src.core.container import container
from src.core.exceptions import ConfigurationError
from src.core.logging import get_logger
from src.data.contracts import RetrievalFilter
from src.rag.contracts import Retriever

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "eval" / "golden_dataset.json"
REPORT_PATH = ROOT / "eval" / "results" / "retrieval_eval.json"


def matches(expected: str, retrieved: list[str]) -> bool:
    """Tài liệu mong đợi có nằm trong kết quả không.

    doc_id trong vector store có tiền tố nguồn: `inventory:VOP398`,
    `meeyland:307423640`. Bộ câu hỏi vàng lại ghi mã trần (`VOP398`) vì người
    soạn lấy trực tiếp từ file dữ liệu gốc.

    So khớp cả hai dạng — nếu chỉ so bằng dấu `==` thì câu truy hồi ĐÚNG tài
    liệu vẫn bị tính là trượt, và số đo trở nên vô nghĩa.

    Chỉ chấp nhận đúng một mức nới lỏng này (tiền tố nguồn). Nới thêm nữa là
    tự thổi phồng kết quả.
    """
    if expected in retrieved:
        return True
    suffix = f":{expected}"
    return any(doc_id.endswith(suffix) for doc_id in retrieved)


class CaseResult(BaseModel):
    question: str
    expected_doc_id: str | None
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    passed: bool = False


class RetrievalEvalSummary(BaseModel):
    """Kết quả toàn bộ lượt đo."""

    total_cases: int = 0
    positive_cases: int = 0
    hits: int = 0
    hit_rate: float = 0.0
    coverage_threshold: float = 0.0
    coverage_with_data: list[float] = Field(default_factory=list)
    coverage_without_data: list[float] = Field(default_factory=list)
    results: list[CaseResult] = Field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"Hit@n     : {self.hits}/{self.positive_cases} = {self.hit_rate:.0%}",
            f"Ngưỡng    : {self.coverage_threshold}",
        ]
        if self.coverage_with_data:
            lines.append(
                f"Coverage câu CÓ dữ liệu   : {min(self.coverage_with_data):.3f} – {max(self.coverage_with_data):.3f}"
            )
        if self.coverage_without_data:
            lines.append(
                f"Coverage câu KHÔNG dữ liệu: "
                f"{min(self.coverage_without_data):.3f} – {max(self.coverage_without_data):.3f}"
            )
        if self.coverage_with_data and self.coverage_without_data:
            gap = min(self.coverage_with_data) - max(self.coverage_without_data)
            if gap > 0:
                lines.append(f"→ Hai nhóm tách rời, ngưỡng hợp lý nằm trong khoảng {gap:.3f}")
            else:
                lines.append(
                    "→ ⚠️ Hai nhóm CHỒNG LẤN — không có ngưỡng coverage nào tách được chúng. "
                    "Guardrail dựa riêng coverage sẽ không đáng tin."
                )
        return "\n".join(lines)


async def run_retrieval_eval(top_k: int = 10, top_n: int = 5) -> RetrievalEvalSummary:
    """Chạy eval và ghi kết quả chi tiết ra eval/results/retrieval_eval.json."""
    configure()
    settings = container.resolve(Settings)

    if not settings.has_openai_key:
        raise ConfigurationError("Eval cần OPENAI_API_KEY hợp lệ để embed câu hỏi như lúc chạy thật.")
    if not GOLDEN_PATH.exists():
        raise ConfigurationError(f"Không tìm thấy bộ câu hỏi vàng: {GOLDEN_PATH}")

    retriever: Retriever = container.resolve(Retriever)
    golden_set = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    eval_filter = RetrievalFilter(visibility=["public", "internal"])

    summary = RetrievalEvalSummary(
        total_cases=len(golden_set),
        coverage_threshold=settings.coverage_threshold,
    )

    for case in golden_set:
        result = await retriever.retrieve(case["question"], top_k=top_k, top_n=top_n, filters=eval_filter)
        retrieved = [chunk.doc_id for chunk in result.chunks]
        expected = case.get("expected_doc_id")

        if expected is None:
            # Câu bẫy: đúng khi độ phủ thấp hơn ngưỡng, tức agent sẽ từ chối.
            passed = result.coverage < settings.coverage_threshold
            summary.coverage_without_data.append(result.coverage)
        else:
            summary.positive_cases += 1
            passed = matches(expected, retrieved)
            summary.hits += int(passed)
            summary.coverage_with_data.append(result.coverage)

        summary.results.append(
            CaseResult(
                question=case["question"],
                expected_doc_id=expected,
                retrieved_doc_ids=retrieved,
                coverage=round(result.coverage, 3),
                passed=passed,
            )
        )
        logger.info("[%s] %s (coverage %.2f)", "OK  " if passed else "MISS", case["question"][:60], result.coverage)

    summary.hit_rate = summary.hits / summary.positive_cases if summary.positive_cases else 0.0

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Chi tiết từng câu: %s", REPORT_PATH)
    return summary
