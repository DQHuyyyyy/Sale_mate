"""Nạp dữ liệu vào vector store — pipeline dùng chung + bốn nguồn.

Trước đây mỗi nguồn là một script riêng trong `scripts/`, và cả bốn script đều
tự dựng lại Embedder + VectorStore + IngestPipeline y hệt nhau. Hậu quả thật:
script tự tạo `QdrantVectorStore` nên chạy tốt, còn `bootstrap.py` vẫn dùng
`InMemoryVectorStore` — web app đứt khỏi dữ liệu suốt nhiều ngày mà không ai
phát hiện, vì không có đường chạy nào đi qua cùng một cấu hình.

Giờ mọi nguồn đi qua `build_pipeline()`, lấy dịch vụ từ container giống hệt
ứng dụng. Ingest và app không thể lệch cấu hình nữa.

Thêm nguồn mới: viết một hàm `ingest_<tên>()` rồi thêm một dòng vào SOURCES.

Chạy:
    python -m src.cli ingest inventory
    python -m src.cli ingest --all
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel

from src.bootstrap import configure
from src.core.config import Settings
from src.core.container import container
from src.core.exceptions import ConfigurationError
from src.core.logging import get_logger
from src.data.contracts import Embedder, LoadedDocument, VectorStore
from src.data.ingestion.chunkers import ParagraphChunker
from src.data.pipeline import IngestPipeline

logger = get_logger(__name__)


class IngestResult(BaseModel):
    """Kết quả một lượt nạp."""

    source: str
    documents: int = 0
    chunks: int = 0
    total_in_store: int = 0

    def summary(self) -> str:
        return (
            f"{self.source}: {self.documents} tài liệu → {self.chunks} chunk (collection hiện có {self.total_in_store})"
        )


def build_pipeline() -> tuple[IngestPipeline, VectorStore, Settings]:
    """Dựng pipeline từ container.

    Raises:
        ConfigurationError: khi chưa có OPENAI_API_KEY hợp lệ.

    Vì sao chặn thay vì rơi về FakeEmbedder như các script cũ: FakeEmbedder sinh
    vector 64 chiều, còn collection thật là 1536 chiều. Ghi vào là hỏng dữ liệu
    hoặc vỡ giữa chừng. Thà dừng ngay với thông báo rõ ràng.
    """
    configure()
    settings = container.resolve(Settings)

    if not settings.has_openai_key:
        raise ConfigurationError("Nạp dữ liệu cần OPENAI_API_KEY hợp lệ để sinh embedding. Điền vào .env rồi chạy lại.")

    embedder = container.resolve(Embedder)
    store = container.resolve(VectorStore)
    pipeline = IngestPipeline(ParagraphChunker(), embedder, store)

    logger.info(
        "Pipeline sẵn sàng",
        extra={
            "context": {
                "store": type(store).__name__,
                "collection": settings.qdrant_collection,
                "embedding_model": settings.embedding_model,
            }
        },
    )
    return pipeline, store, settings


async def ingest_documents(
    source: str,
    documents: list[LoadedDocument],
    pipeline: IngestPipeline,
    store: VectorStore,
) -> IngestResult:
    """Nạp một danh sách tài liệu và trả về số liệu."""
    if not documents:
        logger.warning("Nguồn %s không có tài liệu nào để nạp", source)
        return IngestResult(source=source, total_in_store=await store.count())

    total_chunks = 0
    for document in documents:
        report = await pipeline.ingest_document(document)
        total_chunks += report.chunks

    result = IngestResult(
        source=source,
        documents=len(documents),
        chunks=total_chunks,
        total_in_store=await store.count(),
    )
    logger.info(result.summary())
    return result


RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


async def ingest_inventory(pipeline: IngestPipeline, store: VectorStore) -> IngestResult:
    """Tồn kho 100 căn từ CSV nội bộ.

    Đây là dữ liệu `internal` — chỉ Admin/Sale truy hồi được, portal công khai
    không tìm ra.
    """
    from src.data.sources.inventory import load_inventory_csv, units_to_documents

    units = load_inventory_csv()
    logger.info("Đọc %d căn từ CSV tồn kho", len(units))
    return await ingest_documents("inventory", units_to_documents(units), pipeline, store)


async def ingest_batdongsan(pipeline: IngestPipeline, store: VectorStore) -> IngestResult:
    """Tin đăng batdongsan.com.vn lưu tay.

    Site chặn bot nên không crawl tự động được — dữ liệu là file .html người
    dùng tự lưu bằng trình duyệt (Ctrl+S → "Chỉ HTML"). "Khu nào ra khu đấy":
    mỗi dự án một thư mục riêng, đọc KHÔNG đệ quy (`load_saved_detail_pages`
    dùng `glob` chứ không `rglob`) nên không lẫn dự án dù cùng nằm dưới
    `data/raw/`:
        data/raw/                → OCP1 (Gia Lâm) — thư mục gốc, chỗ cũ
        data/raw/batdongsan_ocp2/ → OCP2 (The Empire, Văn Giang)
        data/raw/batdongsan_ocp3/ → OCP3 (The Crown, Văn Lâm)
    Thư mục OCP2/OCP3 chưa có file nào cho tới khi người dùng tự lưu — không
    có file thì đọc ra danh sách rỗng, không phải lỗi.
    """
    from src.data.crawling.batdongsan import DEFAULT_PROJECT, load_saved_detail_pages

    documents = load_saved_detail_pages(RAW_DIR, DEFAULT_PROJECT)
    documents += load_saved_detail_pages(RAW_DIR / "batdongsan_ocp2", "Vinhomes Ocean Park 2 (The Empire)")
    documents += load_saved_detail_pages(RAW_DIR / "batdongsan_ocp3", "Vinhomes Ocean Park 3 (The Crown)")
    logger.info("Đọc %d tin batdongsan.com.vn đã lưu (cả 3 dự án)", len(documents))
    return await ingest_documents("batdongsan", documents, pipeline, store)


async def ingest_meeyland(pipeline: IngestPipeline, store: VectorStore) -> IngestResult:
    """Tin đăng meeyland.com — crawl trực tiếp, site không chặn bot.

    Crawl CẢ 3 dự án (OCP1 Gia Lâm, OCP2 The Empire, OCP3 The Crown) — mỗi dự
    án qua đúng category/`ProjectConfig` riêng của nó ("khu nào ra khu đấy",
    xem docstring `src/data/crawling/meeyland.py`), gộp kết quả rồi nạp chung
    một lượt. Gộp thành 1 batch — không tách 3 hàm ingest riêng — vì
    `_mark_removed_listings` so sánh với TOÀN BỘ tin `source_site=meeyland.com`
    đang active trên Qdrant: nếu chạy riêng từng dự án, dự án không được crawl
    trong lượt đó sẽ bị hiểu nhầm là "đã gỡ khỏi site" và bị đánh inactive oan.

    Sau khi nạp, tin nào không còn trên site sẽ bị đánh dấu `is_active=False`
    thay vì xoá — giữ làm lịch sử, và truy hồi chỉ lấy bản còn hiệu lực.
    """
    from src.data.crawling import meeyland

    documents: list[LoadedDocument] = []
    for project, limits in (
        (meeyland.PROJECT_OCP1, meeyland.CrawlLimits(max_search_pages=20, max_listings=None)),
        (meeyland.PROJECT_OCP2, meeyland.CrawlLimits(max_search_pages=20, max_listings=None)),
        # OCP3 chưa có category riêng cho căn hộ (0 tin, xem docstring
        # meeyland.py) — category dùng tạm là cấp huyện, phải lọc must_mention
        # nên giới hạn số trang thấp hơn để không quét quá nhiều tin không liên quan.
        (meeyland.PROJECT_OCP3, meeyland.CrawlLimits(max_search_pages=10, max_listings=None)),
    ):
        project_documents = await meeyland.crawl_vinhomes_ocean_park(limits, project)
        logger.info("Crawl được %d tin meeyland.com cho %s", len(project_documents), project.project_name)
        documents.extend(project_documents)

    result = await ingest_documents("meeyland", documents, pipeline, store)

    await _mark_removed_listings(store, documents, source_site="meeyland.com")
    return result


async def ingest_knowledge(pipeline: IngestPipeline, store: VectorStore) -> IngestResult:
    """Tài liệu kiến thức chung: chính sách, thủ tục, tiện ích, pháp lý.

    Mỗi file .md phải có front-matter title/section/visibility — thiếu là báo
    lỗi ngay, tránh gắn nhầm quyền cho nội dung nội bộ.
    """
    from src.data.ingestion.metadata_schema import validate_metadata
    from src.data.sources.knowledge_docs import load_knowledge_dir

    documents = load_knowledge_dir()
    logger.info("Đọc %d tài liệu kiến thức chung", len(documents))

    for document in documents:
        validate_metadata(document.metadata, doc_id=document.doc_id)

    return await ingest_documents("knowledge", documents, pipeline, store)


async def _mark_removed_listings(store: VectorStore, documents: list, source_site: str) -> None:
    """Đánh dấu tin đã bị gỡ khỏi site nguồn là hết hiệu lực."""
    mark_inactive = getattr(store, "mark_inactive", None)
    list_active = getattr(store, "list_active_doc_ids", None)
    if mark_inactive is None or list_active is None:
        return  # store trong bộ nhớ không hỗ trợ — bỏ qua, không phải lỗi

    current = {document.doc_id for document in documents}
    stale = await list_active(source_site) - current
    if stale:
        await mark_inactive(list(stale))
        logger.info("Đánh dấu %d tin %s đã gỡ khỏi site là hết hiệu lực", len(stale), source_site)


SOURCES: dict[str, Callable[[IngestPipeline, VectorStore], Awaitable[IngestResult]]] = {
    "inventory": ingest_inventory,
    "batdongsan": ingest_batdongsan,
    "meeyland": ingest_meeyland,
    "knowledge": ingest_knowledge,
}
