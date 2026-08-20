"""Dòng lệnh quản lý lõi AI.

Thay cho 5 script rời trong `scripts/` trước đây. Mọi lệnh đều đi qua
`bootstrap.configure()` nên dùng đúng cấu hình mà ứng dụng đang dùng — không thể
xảy ra chuyện lệnh ghi vào Qdrant còn web app đọc từ chỗ khác.

    python -m src.cli status                # vector store đang có gì
    python -m src.cli ingest inventory      # nạp một nguồn
    python -m src.cli ingest --all          # nạp tất cả
    python -m src.cli search "câu hỏi"      # thử truy hồi
    python -m src.cli eval retrieval        # đo tầng truy hồi
    python -m src.cli eval answer --compare v6 v7   # đo prompt, so trước/sau

Đặt ở gốc `src/` chứ không trong `src/data/` vì nó gọi cả ba tầng: data (ingest),
rag (search) và eval. Để trong data/ thì data phải import rag, phá quy tắc phụ
thuộc một chiều rag → data.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.agents.prompts import SYSTEM_PROMPT_VERSION
from src.bootstrap import configure
from src.core.config import Settings
from src.core.container import container
from src.core.exceptions import SalesMateError
from src.core.logging import setup_logging
from src.data.contracts import RetrievalFilter, VectorStore
from src.data.ingest import SOURCES, build_pipeline
from src.rag.contracts import Retriever


async def cmd_ingest(names: list[str]) -> int:
    pipeline, store, settings = build_pipeline()
    print(f"Collection: {settings.qdrant_collection}  ({type(store).__name__})\n")

    for name in names:
        handler = SOURCES[name]
        print(f"→ Đang nạp nguồn '{name}' …")
        result = await handler(pipeline, store)
        print(f"  {result.summary()}\n")
    return 0


async def cmd_status() -> int:
    configure()
    settings = container.resolve(Settings)
    store = container.resolve(VectorStore)
    total = await store.count()

    print(f"Vector store : {type(store).__name__}")
    print(f"Collection   : {settings.qdrant_collection}")
    print(f"Số chunk     : {total}")
    print(f"Embedding    : {settings.embedding_model} ({settings.embedding_dim} chiều)")
    print(f"RAG          : {'bật' if settings.enable_rag else 'TẮT'}")
    print(f"Reranker     : {settings.reranker}")
    if total == 0:
        print("\n⚠️  Chưa có dữ liệu. Chạy: python -m src.data.cli ingest --all")
    return 0


async def cmd_search(question: str, internal: bool) -> int:
    configure()
    retriever = container.resolve(Retriever)
    visibility = ["public", "internal"] if internal else ["public"]
    result = await retriever.retrieve(question, filters=RetrievalFilter(visibility=visibility))  # type: ignore[arg-type]

    print(f"Câu hỏi : {question}")
    print(f"Quyền   : {', '.join(visibility)}")
    print(f"Độ phủ  : {result.coverage:.3f}\n")
    if not result.chunks:
        print("Không truy hồi được chunk nào.")
        return 0
    for index, chunk in enumerate(result.chunks, start=1):
        print(f"{index}. [{chunk.score:.3f}] {chunk.doc_title[:60]}  ({chunk.visibility})")
        print(f"   {chunk.text[:140].strip()}…\n")
    return 0


async def cmd_eval() -> int:
    from src.eval.retrieval import run_retrieval_eval

    summary = await run_retrieval_eval()
    print()
    print(summary.report())
    return 0


async def cmd_eval_answer(
    prompt_version: str,
    compare: list[str] | None,
    label: str | None = None,
    doi_chieu: list[str] | None = None,
) -> int:
    """Đo quyết định trả lời/từ chối trên bộ câu hỏi đối kháng.

    Ba cách dùng, khác nhau ở chỗ so cái gì:

    - `--compare v6 v7` chạy hai bản PROMPT trong cùng một lượt. Chỉ hợp khi
      biến duy nhất là prompt.
    - `--label X` chạy một lượt rồi ghi ra `answer_eval_X.json`. Dùng khi biến
      là MODEL hoặc cờ môi trường — những thứ đọc từ `Settings`, mà một tiến
      trình chỉ có một `Settings`.
    - `--doi-chieu X Y` đọc lại hai file đã ghi rồi in bảng, không gọi model.
      Đây là cách so hai cấu hình model, và nó không tốn thêm đồng nào.
    """
    from src.eval.answer import doc_ket_qua, run_answer_eval, so_sanh

    if doi_chieu:
        print()
        print(so_sanh(doc_ket_qua(doi_chieu[0]), doc_ket_qua(doi_chieu[1])))
        return 0

    if compare:
        truoc = await run_answer_eval(compare[0])
        sau = await run_answer_eval(compare[1])
        print()
        print(so_sanh(truoc, sau))
        return 0

    tong_ket = await run_answer_eval(prompt_version, nhan=label)
    print()
    print(tong_ket.bang())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Nạp dữ liệu vào vector store")
    ingest.add_argument("sources", nargs="*", choices=[*SOURCES, []], help="Tên nguồn cần nạp")
    ingest.add_argument("--all", action="store_true", help="Nạp toàn bộ nguồn")

    sub.add_parser("status", help="Xem vector store đang có gì")

    search = sub.add_parser("search", help="Thử truy hồi một câu hỏi")
    search.add_argument("question")
    search.add_argument("--internal", action="store_true", help="Cho phép đọc cả tài liệu nội bộ")

    evaluate = sub.add_parser("eval", help="Đo chất lượng trên bộ câu hỏi vàng")
    evaluate.add_argument(
        "target",
        nargs="?",
        default="retrieval",
        choices=["retrieval", "answer"],
        help="retrieval = đo tầng truy hồi (không gọi LLM); answer = đo quyết định trả lời/từ chối",
    )
    evaluate.add_argument(
        "--prompt-version",
        default=SYSTEM_PROMPT_VERSION,
        help="Bản prompt đem đo, ví dụ v6. Mặc định là bản đang chạy.",
    )
    evaluate.add_argument(
        "--compare",
        nargs=2,
        metavar=("TRUOC", "SAU"),
        help="Chạy hai bản prompt trên cùng bộ câu hỏi rồi in bảng trước/sau",
    )
    evaluate.add_argument(
        "--label",
        help="Nhãn của lần chạy, dùng đặt tên file kết quả. Dùng khi biến là model chứ không phải prompt.",
    )
    evaluate.add_argument(
        "--doi-chieu",
        nargs=2,
        metavar=("NHAN_A", "NHAN_B"),
        help="So hai lần chạy ĐÃ GHI ra file, không gọi model lần nào",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging("INFO")
    args = build_parser().parse_args(argv)

    try:
        if args.command == "ingest":
            names = list(SOURCES) if args.all else [n for n in args.sources if n]
            if not names:
                print("Chọn nguồn cần nạp, hoặc dùng --all.")
                print(f"Nguồn có sẵn: {', '.join(SOURCES)}")
                return 1
            return asyncio.run(cmd_ingest(names))
        if args.command == "status":
            return asyncio.run(cmd_status())
        if args.command == "search":
            return asyncio.run(cmd_search(args.question, args.internal))
        if args.command == "eval":
            if args.target == "answer":
                return asyncio.run(cmd_eval_answer(args.prompt_version, args.compare, args.label, args.doi_chieu))
            return asyncio.run(cmd_eval())
    except SalesMateError as exc:
        print(f"\n✗ {exc.message}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
