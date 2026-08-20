"""Test endpoint đọc tài liệu — nguồn cho nút trích dẫn bấm được.

Đọc từ FILE chứ không từ Qdrant: `VectorStore` Protocol không có hàm liệt kê
tài liệu, và `data/contracts.py` là file đóng băng. `doc_id` sinh từ tên file
nên định danh vẫn khớp một-đối-một với thứ Qdrant giữ.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_liet_ke_tra_ve_moi_tai_lieu(client) -> None:
    r = await client.get("/api/v1/documents")

    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert all(d["doc_id"].startswith("knowledge:") for d in r.json())


@pytest.mark.asyncio
async def test_danh_sach_khong_cho_noi_dung(client) -> None:
    """11 tài liệu kèm toàn văn là vài chục KB cho một màn chỉ hiện tiêu đề."""
    r = await client.get("/api/v1/documents")

    assert "noi_dung" not in r.json()[0]
    assert r.json()[0]["so_ky_tu"] > 0


@pytest.mark.asyncio
async def test_doc_toan_van_theo_doc_id(client) -> None:
    ds = (await client.get("/api/v1/documents")).json()
    doc_id = ds[0]["doc_id"]

    r = await client.get(f"/api/v1/documents/{doc_id}")

    assert r.status_code == 200
    assert len(r.json()["noi_dung"]) == ds[0]["so_ky_tu"]


@pytest.mark.asyncio
async def test_doc_id_co_dau_hai_cham_va_dau_tieng_viet(client) -> None:
    """`:path` là bắt buộc — `doc_id` có dấu hai chấm, khoảng trắng và dấu.

    Thiếu nó thì Starlette cắt sai và mọi nút trích nguồn dẫn tới 404.
    """
    ds = (await client.get("/api/v1/documents")).json()
    co_dau = [d for d in ds if " " in d["doc_id"]]
    if not co_dau:
        pytest.skip("Không có tài liệu nào tên chứa khoảng trắng")

    r = await client.get(f"/api/v1/documents/{co_dau[0]['doc_id']}")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_khong_co_thi_tra_404_chu_khong_no(client) -> None:
    r = await client.get("/api/v1/documents/knowledge:khong-bao-gio-ton-tai")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_kem_phien_ban_de_thay_lech_voi_qdrant(client) -> None:
    """Sửa file mà quên `ingest` thì trang hiện bản mới còn trợ lý đọc bản cũ.
    `version` là thứ duy nhất làm chênh lệch đó nhìn thấy được."""
    r = await client.get("/api/v1/documents")

    assert all(d["version"] for d in r.json())
