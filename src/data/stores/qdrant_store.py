"""VectorStore chạy trên Qdrant — dùng cho staging/production.

Vì sao Qdrant thay vì Chroma: payload filtering mạnh, cho phép lọc phân quyền
(visibility, is_active) NGAY trong truy vấn vector thay vì lọc sau. Xem ADR-001.

Cần Qdrant đang chạy: docker compose up -d qdrant
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from src.core.exceptions import UpstreamError
from src.core.logging import get_logger
from src.data.contracts import Chunk, RetrievalFilter

logger = get_logger(__name__)


class QdrantVectorStore:
    """Cài đặt VectorStore trên Qdrant."""

    def __init__(
        self,
        url: str,
        collection: str,
        *,
        api_key: str = "",
        client: AsyncQdrantClient | None = None,
    ) -> None:
        self._collection = collection
        self._client = client or AsyncQdrantClient(url=url, api_key=api_key or None)

    async def ensure_collection(self, dimension: int) -> None:
        try:
            exists = await self._client.collection_exists(self._collection)
            if exists:
                return
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            # Index cho các trường lọc phân quyền — bắt buộc để filter nhanh.
            for field, schema in (
                ("visibility", models.PayloadSchemaType.KEYWORD),
                ("is_active", models.PayloadSchemaType.BOOL),
                ("doc_id", models.PayloadSchemaType.KEYWORD),
                ("project", models.PayloadSchemaType.KEYWORD),
            ):
                await self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=schema,
                )
            logger.info("Đã tạo collection Qdrant %s (dim=%d)", self._collection, dimension)
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
            await self._client.upsert(collection_name=self._collection, points=points)
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
        try:
            response = await self._client.query_points(
                collection_name=self._collection,
                query=vector,
                query_filter=_to_qdrant_filter(filters),
                limit=limit,
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Truy vấn Qdrant thất bại.") from exc

        return [_from_payload(point.payload or {}, point.score) for point in response.points]

    async def delete_by_doc(self, doc_id: str) -> int:
        try:
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


def _point_id(chunk_id: str) -> str:
    """Qdrant nhận UUID hoặc số nguyên — chuyển id chuỗi thành UUID ổn định."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _to_payload(chunk: Chunk) -> dict[str, Any]:
    payload = chunk.model_dump(exclude={"score"})
    # Đưa project lên payload gốc để index lọc được.
    payload["project"] = chunk.metadata.get("project")
    return payload


def _from_payload(payload: dict[str, Any], score: float) -> Chunk:
    data = {key: value for key, value in payload.items() if key != "project"}
    data.setdefault("metadata", {})
    if payload.get("project") is not None:
        data["metadata"] = {**data["metadata"], "project": payload["project"]}
    return Chunk(**data, score=score)


def _to_qdrant_filter(filters: RetrievalFilter) -> models.Filter:
    """Dịch RetrievalFilter sang filter Qdrant — nơi phân quyền thực sự xảy ra."""
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
    for key, value in filters.extra.items():
        must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=must)
