"""Test endpoint dữ liệu portal."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_listings_returns_items(client):
    response = await client.get("/api/v1/listings")

    assert response.status_code == 200
    items = response.json()
    assert items
    assert {"id", "title", "price_label", "location"} <= set(items[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("listing_type", ["sale", "rent", "transfer"])
async def test_listings_filter_by_type(client, listing_type):
    response = await client.get("/api/v1/listings", params={"listing_type": listing_type})

    assert response.status_code == 200
    assert all(item["listing_type"] == listing_type for item in response.json())


@pytest.mark.asyncio
async def test_listings_rejects_unknown_type(client):
    response = await client.get("/api/v1/listings", params={"listing_type": "khong-ton-tai"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_listings_respects_limit(client):
    response = await client.get("/api/v1/listings", params={"limit": 2})

    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_projects_and_demands(client):
    projects = await client.get("/api/v1/projects")
    demands = await client.get("/api/v1/demands")

    assert projects.status_code == 200
    assert demands.status_code == 200
    assert projects.json()[0]["name"]
    assert demands.json()[0]["author_initials"]


@pytest.mark.asyncio
async def test_market_stats_totals_match_bars(client):
    response = await client.get("/api/v1/market")

    assert response.status_code == 200
    body = response.json()
    assert body["listings_today"] == sum(bar["value"] for bar in body["bars"])
    assert len(body["bars"]) == 5
