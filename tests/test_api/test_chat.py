"""Test endpoint chat — cả đường thường lẫn đường SSE."""

from __future__ import annotations

import json

import pytest

from tests.conftest import FAKE_REPLY


@pytest.mark.asyncio
async def test_chat_returns_answer(client):
    response = await client.post("/api/v1/chat", json={"message": "Xin chào"})

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == FAKE_REPLY
    assert body["session_id"]


@pytest.mark.asyncio
async def test_chat_keeps_given_session_id(client):
    response = await client.post("/api/v1/chat", json={"message": "Xin chào", "session_id": "abc-123"})

    assert response.json()["session_id"] == "abc-123"


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.asyncio
async def test_chat_rejects_message_over_limit(client):
    response = await client.post("/api/v1/chat", json={"message": "a" * 2001})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stream_emits_start_tokens_and_done(client):
    events = await _collect_sse(client, {"message": "Xin chào"})

    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "done"

    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert tokens.strip() == FAKE_REPLY


@pytest.mark.asyncio
async def test_stream_shares_one_session_id(client):
    events = await _collect_sse(client, {"message": "Xin chào"})

    session_ids = {event["session_id"] for event in events}
    assert len(session_ids) == 1
    assert session_ids.pop()


async def _collect_sse(client, payload: dict) -> list[dict]:
    """Đọc toàn bộ event từ một response SSE."""
    events: list[dict] = []
    async with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events
