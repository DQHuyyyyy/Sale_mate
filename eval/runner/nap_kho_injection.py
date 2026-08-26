"""Nạp tài liệu test có chèn chỉ dẫn giả vào một collection Qdrant RIÊNG.

Chỉ phục vụ case A02. Plan Ngày 1 nói rõ: không đưa tài liệu injection vào kho
RAG thật — dự án dùng CHUNG một Qdrant cho mọi môi trường, nên nạp nhầm là khách
thật đọc phải nó.

Cách ly bằng `QDRANT_COLLECTION`, không bằng cách tự dựng `QdrantVectorStore`:

    QDRANT_COLLECTION=eval_injection python -m eval.runner.nap_kho_injection

Toàn bộ đường nạp vẫn là `build_pipeline()` + `load_knowledge_dir()` +
`ingest_documents()` của `src/data/`, chỉ đổi thư mục nguồn và collection đích.
Bài học cũ ở CLAUDE.md là bốn script tự dựng store riêng rồi trôi lệch khỏi
`bootstrap.py`; ở đây pipeline vẫn đi qua container nên không tái diễn.

Chốt an toàn: script TỪ CHỐI chạy nếu collection đích trùng collection sản phẩm.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.ingest import build_pipeline, ingest_documents  # noqa: E402
from src.data.sources.knowledge_docs import load_knowledge_dir  # noqa: E402

THU_MUC_TEST = Path(__file__).resolve().parents[1] / "fixtures" / "kho_injection"
COLLECTION_SAN_PHAM = "documents_chunks"


async def nap() -> int:
    pipeline, store, settings = build_pipeline()

    if settings.qdrant_collection == COLLECTION_SAN_PHAM:
        print(
            f"TỪ CHỐI: collection đích đang là '{COLLECTION_SAN_PHAM}' — đó là kho sản phẩm.\n"
            "Chạy lại với QDRANT_COLLECTION=eval_injection.",
            file=sys.stderr,
        )
        return 1

    tai_lieu = load_knowledge_dir(THU_MUC_TEST)
    if not tai_lieu:
        print(f"Không có file .md nào trong {THU_MUC_TEST}", file=sys.stderr)
        return 1

    ket_qua = await ingest_documents("eval_injection", tai_lieu, pipeline, store)
    print(f"Collection '{settings.qdrant_collection}': {ket_qua.summary()}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(nap()))
