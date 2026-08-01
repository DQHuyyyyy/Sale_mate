"""Fixture dùng chung cho toàn bộ test.

Nguyên tắc: KHÔNG test nào được gọi OpenAI hay Qdrant thật. Container được dựng
lại với implementation giả lập trước mỗi test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.agents.contracts import LLMProvider
from src.bootstrap import configure
from src.core.config import Settings
from src.core.container import container
from src.data.contracts import Embedder, VectorStore
from src.data.ingestion.embedders import FakeEmbedder
from src.data.stores.memory_store import InMemoryVectorStore
from src.main import app
from src.services.llm import ScriptedProvider

FAKE_REPLY = "Xin chào, đây là câu trả lời thử nghiệm."


@pytest.fixture
def settings() -> Settings:
    """Settings cho môi trường test — không đọc .env của máy."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        openai_api_key="",  # rỗng ⇒ bootstrap tự chọn ScriptedProvider
        cors_origins="http://localhost:3000",
        coverage_threshold=0.35,
    )


@pytest.fixture(autouse=True)
def configured_container(settings: Settings):
    """Dựng lại container với dịch vụ giả lập trước mỗi test."""
    container.reset()
    configure(container, settings)
    container.override(LLMProvider, ScriptedProvider(FAKE_REPLY, delay_s=0))
    yield container
    container.reset()


@pytest_asyncio.fixture
async def client(configured_container):
    """HTTP client gọi thẳng ASGI app, không cần chạy server thật."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
def fake_embedder() -> Embedder:
    return FakeEmbedder(dimension=32)


@pytest.fixture
def memory_store() -> VectorStore:
    return InMemoryVectorStore()


@pytest.fixture
def scripted_llm() -> LLMProvider:
    return ScriptedProvider(FAKE_REPLY, delay_s=0)
