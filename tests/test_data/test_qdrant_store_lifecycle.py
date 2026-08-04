"""Test vòng đời active/expired của QdrantVectorStore — mục 6 Data Handling.

Không gọi Qdrant thật (đúng quy ước dự án) — dùng client giả tối thiểu, chỉ
mô phỏng đúng 2 lệnh `scroll`/`set_payload` mà `list_active_doc_ids` và
`mark_inactive` thực sự gọi tới.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.data.stores.qdrant_store import QdrantVectorStore


@dataclass
class _FakePoint:
    doc_id: str
    source_site: str
    is_active: bool = True

    @property
    def payload(self) -> dict:
        return {"doc_id": self.doc_id}


@dataclass
class _FakeQdrantClient:
    points: list[_FakePoint] = field(default_factory=list)
    set_payload_calls: list[list[str]] = field(default_factory=list)

    async def scroll(self, *, collection_name, scroll_filter, limit, offset, with_payload):
        conditions = {c.key: c.match.value for c in scroll_filter.must}
        matched = [
            p
            for p in self.points
            if p.source_site == conditions["metadata.source_site"] and p.is_active == conditions["is_active"]
        ]
        return matched, None

    async def set_payload(self, *, collection_name, payload, points):
        doc_ids = list(points.must[0].match.any)
        self.set_payload_calls.append(doc_ids)
        for p in self.points:
            if p.doc_id in doc_ids:
                p.is_active = payload["is_active"]


@pytest.fixture
def fake_client() -> _FakeQdrantClient:
    return _FakeQdrantClient(
        points=[
            _FakePoint(doc_id="meeyland:1", source_site="meeyland.com"),
            _FakePoint(doc_id="meeyland:2", source_site="meeyland.com"),
            _FakePoint(doc_id="batdongsan:1", source_site="batdongsan.com.vn"),
        ]
    )


@pytest.fixture
def store(fake_client: _FakeQdrantClient) -> QdrantVectorStore:
    return QdrantVectorStore("http://fake", "test_collection", client=fake_client)


@pytest.mark.asyncio
async def test_list_active_doc_ids_chi_lay_dung_nguon_va_dang_active(store: QdrantVectorStore):
    ids = await store.list_active_doc_ids("meeyland.com")

    assert ids == {"meeyland:1", "meeyland:2"}


@pytest.mark.asyncio
async def test_mark_inactive_danh_dau_dung_doc_khong_dong_toi_nguon_khac(
    store: QdrantVectorStore, fake_client: _FakeQdrantClient
):
    count = await store.mark_inactive(["meeyland:1"])

    assert count == 1
    active_after = {p.doc_id for p in fake_client.points if p.is_active}
    assert active_after == {"meeyland:2", "batdongsan:1"}


@pytest.mark.asyncio
async def test_mark_inactive_danh_sach_rong_khong_goi_client(store: QdrantVectorStore, fake_client: _FakeQdrantClient):
    count = await store.mark_inactive([])

    assert count == 0
    assert fake_client.set_payload_calls == []
