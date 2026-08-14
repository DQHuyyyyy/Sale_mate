"""VectorStore chạy trên Qdrant — dùng cho staging/production.

Vì sao Qdrant thay vì Chroma: payload filtering mạnh, cho phép lọc phân quyền
(visibility, is_active) NGAY trong truy vấn vector thay vì lọc sau. Xem ADR-001.

Cần Qdrant đang chạy: docker compose up -d qdrant
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.exceptions import UpstreamError
from src.core.logging import get_logger
from src.data.contracts import Chunk, RetrievalFilter

logger = get_logger(__name__)

# Qdrant Cloud thỉnh thoảng treo request (ReadTimeout) khi ghi/xoá hàng loạt
# điểm liên tiếp — quan sát thật khi chạy ingest thật (không phải giả định).
# Thử lại tối đa 3 lần, chỉ với lỗi mạng/timeout, không nuốt lỗi nghiệp vụ khác.
_RETRYABLE_EXC = (httpx.TimeoutException, ResponseHandlingException)
_UPSERT_BATCH_SIZE = 100


def _retrying() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE_EXC),
        reraise=True,
    )


class QdrantVectorStore:
    """Cài đặt VectorStore trên Qdrant."""

    def __init__(
        self,
        url: str,
        collection: str,
        *,
        api_key: str = "",
        timeout: float = 30.0,
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._collection = collection
        # qdrant-client mặc định chờ 5 giây. Với Qdrant Cloud, lần gọi đầu sau
        # một lúc không dùng phải bắt tay TLS và đánh thức cluster nên hay vượt
        # mức đó — biểu hiện là hỏi lần đầu báo "chưa đủ dữ liệu", hỏi lại đúng
        # câu đó thì trả lời được. Ghi/xoá hàng loạt điểm liên tiếp cũng dễ vượt
        # mức 5s mặc định — nâng default lên 30s, vẫn cho override qua tham số.
        self._client = client or AsyncQdrantClient(url=url, api_key=api_key or None, timeout=timeout)

    async def ensure_collection(self, dimension: int) -> None:
        try:
            exists = await self._client.collection_exists(self._collection)
            if not exists:
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info("Đã tạo collection Qdrant %s (dim=%d)", self._collection, dimension)

            # Luôn đảm bảo đủ index, kể cả khi collection đã tồn tại từ trước —
            # KHÔNG return sớm ở nhánh exists=True như bản cũ. Bug thật phát
            # hiện 11/08/2026: thêm field lọc mới (price/area/num_bedrooms...)
            # vào danh sách dưới đây không có tác dụng gì trên collection đã
            # tồn tại, vì nhánh cũ chỉ tạo index lúc tạo MỚI collection — âm
            # thầm để field lọc không hoạt động cho tới khi ai đó xoá hẳn
            # collection rồi tạo lại. `create_payload_index` là thao tác
            # idempotent (gọi lại trên field đã có index không lỗi), nên chạy
            # lại mỗi lần không tốn kém, không có tác dụng phụ.
            #
            # Index cho các trường lọc phân quyền, lọc cấu trúc bất động sản,
            # và metadata.source_site — bắt buộc để filter nhanh. Qdrant Cloud
            # (khác local Docker) từ chối filter trên field chưa có index với
            # lỗi 400 — cần cho list_active_doc_ids() (mục 6 active/expired).
            for field, schema in (
                ("visibility", models.PayloadSchemaType.KEYWORD),
                ("is_active", models.PayloadSchemaType.BOOL),
                ("doc_id", models.PayloadSchemaType.KEYWORD),
                ("project", models.PayloadSchemaType.KEYWORD),
                ("price", models.PayloadSchemaType.FLOAT),
                ("area", models.PayloadSchemaType.FLOAT),
                ("num_bedrooms", models.PayloadSchemaType.INTEGER),
                ("building", models.PayloadSchemaType.KEYWORD),
                ("property_type", models.PayloadSchemaType.KEYWORD),
                ("doc_kind", models.PayloadSchemaType.KEYWORD),
                ("metadata.source_site", models.PayloadSchemaType.KEYWORD),
            ):
                await self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=schema,
                )
        except Exception as exc:  # noqa: BLE001 - gói lại thành lỗi nghiệp vụ
            raise UpstreamError("Không kết nối được Qdrant.", detail={"cause": str(exc)}) from exc

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("Số chunk và số vector phải bằng nhau")
        points = [
            models.PointStruct(
                id=_point_id(chunk.id),
                vector=vector,
                payload=_to_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            # Một request chứa cả trăm điểm dễ vượt timeout trên Qdrant Cloud
            # dù đã retry (quan sát thật: 637 điểm trong 1 request timeout cả
            # 3 lần thử) — chia nhỏ theo lô để mỗi request nhanh và ổn định.
            for i in range(0, len(points), _UPSERT_BATCH_SIZE):
                batch = points[i : i + _UPSERT_BATCH_SIZE]
                async for attempt in _retrying():
                    with attempt:
                        await self._client.upsert(collection_name=self._collection, points=batch)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Ghi dữ liệu vào Qdrant thất bại.") from exc
        return len(points)

    async def search(
        self,
        vector: list[float],
        *,
        filters: RetrievalFilter,
        limit: int,
    ) -> list[Chunk]:
        # Thử lại đúng MỘT lần. Lần gọi đầu tới Qdrant Cloud sau một lúc không
        # dùng hay hết thời gian chờ, nhưng chính nó đã dựng xong kết nối nên
        # lần thứ hai gần như luôn nhanh. Không có bước này thì người dùng phải
        # tự hỏi lại câu vừa hỏi — đúng lỗi đã gặp trên production.
        loi_cuoi: Exception | None = None
        for lan in range(2):
            try:
                response = await self._client.query_points(
                    collection_name=self._collection,
                    query=vector,
                    query_filter=_to_qdrant_filter(filters),
                    limit=limit,
                    with_payload=True,
                )
            except Exception as exc:  # noqa: BLE001 - gói lại thành lỗi nghiệp vụ ở dưới
                loi_cuoi = exc
                logger.warning("Truy vấn Qdrant hỏng (lần %s/2): %s", lan + 1, exc)
                continue
            return [_from_payload(point.payload or {}, point.score) for point in response.points]

        raise UpstreamError("Truy vấn Qdrant thất bại.") from loi_cuoi

    async def delete_by_doc(self, doc_id: str) -> int:
        try:
            async for attempt in _retrying():
                with attempt:
                    await self._client.delete(
                        collection_name=self._collection,
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]
                            )
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Xoá dữ liệu trên Qdrant thất bại.") from exc
        return 1

    async def count(self) -> int:
        try:
            result = await self._client.count(collection_name=self._collection, exact=True)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Đếm điểm trên Qdrant thất bại.") from exc
        return result.count

    async def list_active_doc_ids(self, source_site: str) -> set[str]:
        """Liệt kê doc_id đang active của một nguồn — dùng để so sánh với lần
        crawl mới nhất, phát hiện tin đã bị gỡ khỏi nguồn (mục 6 Data
        Handling: trạng thái active/expired). KHÔNG thuộc `VectorStore`
        Protocol (contracts.py đóng băng) — chỉ dùng nội bộ trong scripts
        ingest của module data, module khác không được gọi trực tiếp.
        """
        doc_ids: set[str] = set()
        offset = None
        query_filter = models.Filter(
            must=[
                models.FieldCondition(key="metadata.source_site", match=models.MatchValue(value=source_site)),
                models.FieldCondition(key="is_active", match=models.MatchValue(value=True)),
            ]
        )
        try:
            while True:
                points, offset = await self._client.scroll(
                    collection_name=self._collection,
                    scroll_filter=query_filter,
                    limit=200,
                    offset=offset,
                    with_payload=["doc_id"],
                )
                # pyrefly: ignore [unsupported-operation]
                doc_ids.update(point.payload["doc_id"] for point in points)
                if offset is None:
                    break
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Liệt kê doc_id trên Qdrant thất bại.") from exc
        return doc_ids

    async def mark_inactive(self, doc_ids: list[str]) -> int:
        """Đánh dấu is_active=False cho các doc_id — dùng khi tin đã bị gỡ
        khỏi nguồn. Chỉ sửa payload (không cần vector), giữ nguyên text cũ
        làm lịch sử thay vì xoá hẳn như `delete_by_doc`. Không thuộc
        `VectorStore` Protocol, cùng lý do như `list_active_doc_ids`.
        """
        if not doc_ids:
            return 0
        try:
            await self._client.set_payload(
                collection_name=self._collection,
                payload={"is_active": False},
                points=models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids))]),
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Đánh dấu is_active=False trên Qdrant thất bại.") from exc
        return len(doc_ids)


def _point_id(chunk_id: str) -> str:
    """Qdrant nhận UUID hoặc số nguyên — chuyển id chuỗi thành UUID ổn định."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


_STRUCTURED_KEYS = ("project", "price", "area", "num_bedrooms", "building", "property_type", "doc_kind")


def _to_payload(chunk: Chunk) -> dict[str, Any]:
    payload = chunk.model_dump(exclude={"score"})
    # Đưa các trường cấu trúc lên payload gốc để Qdrant index và lọc trực tiếp.
    for key in _STRUCTURED_KEYS:
        if key in chunk.metadata:
            payload[key] = chunk.metadata[key]
    return payload


def _from_payload(payload: dict[str, Any], score: float) -> Chunk:
    data = {key: value for key, value in payload.items() if key not in _STRUCTURED_KEYS}
    data.setdefault("metadata", {})
    for key in _STRUCTURED_KEYS:
        if payload.get(key) is not None:
            data["metadata"][key] = payload[key]
    return Chunk(**data, score=score)


def _to_qdrant_filter(filters: RetrievalFilter) -> models.Filter:
    """Dịch RetrievalFilter sang filter Qdrant — phân quyền và lọc cấu trúc bất động sản."""
    must: list[models.Condition] = [
        models.FieldCondition(
            key="visibility",
            match=models.MatchAny(any=list(filters.visibility)),
        )
    ]
    if filters.is_active:
        must.append(models.FieldCondition(key="is_active", match=models.MatchValue(value=True)))
    if filters.project is not None:
        must.append(models.FieldCondition(key="project", match=models.MatchValue(value=filters.project)))
    if filters.doc_ids is not None:
        must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=filters.doc_ids)))
    if filters.doc_kind is not None:
        must.append(models.FieldCondition(key="doc_kind", match=models.MatchValue(value=filters.doc_kind)))

    # Lọc khoảng giá
    if filters.min_price is not None or filters.max_price is not None:
        must.append(
            models.FieldCondition(
                key="price",
                range=models.Range(gte=filters.min_price, lte=filters.max_price),
            )
        )

    # Lọc khoảng diện tích
    if filters.min_area is not None or filters.max_area is not None:
        must.append(
            models.FieldCondition(
                key="area",
                range=models.Range(gte=filters.min_area, lte=filters.max_area),
            )
        )

    # Lọc số phòng
    if filters.num_bedrooms is not None:
        must.append(models.FieldCondition(key="num_bedrooms", match=models.MatchValue(value=filters.num_bedrooms)))

    # Lọc Tòa
    if filters.building is not None:
        must.append(models.FieldCondition(key="building", match=models.MatchValue(value=filters.building)))

    # Lọc Loại căn
    if filters.property_type is not None:
        must.append(models.FieldCondition(key="property_type", match=models.MatchValue(value=filters.property_type)))

    for key, value in filters.extra.items():
        must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=must)
