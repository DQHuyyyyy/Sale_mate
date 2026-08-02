"""Test health check."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_root_health(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_v1_health_reports_checks(client):
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["agent"] == "ready"


@pytest.mark.asyncio
async def test_liveness(client):
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
