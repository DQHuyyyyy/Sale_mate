"""Fixture dùng chung cho toàn bộ test.

Nguyên tắc: KHÔNG test nào được gọi OpenAI, Qdrant hay Postgres thật. Container
được dựng lại với implementation giả lập trước mỗi test.
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


@pytest.fixture(autouse=True)
def _chan_postgres_that(monkeypatch):
    """Tồn kho luôn là SQLite RỖNG trong bộ nhớ, trừ khi test tự nạp dữ liệu.

    Tool tồn kho gọi `get_inventory_db()`, hàm này đọc `get_settings()` toàn
    cục — tức là `.env` của máy, tức là Supabase THẬT. Không chặn ở đây thì bất
    kỳ test nào vô tình chạm vào tool đều bắn thẳng vào database production, và
    nó đã xảy ra thật: thêm tool `inventory_search` làm một test grounding cũ
    bỗng nhiên gọi Supabase rồi đổi kết quả.

    Test nào cần dữ liệu tồn kho thì tự monkeypatch `get_inventory_db` trong
    module của mình, đè lên fixture này.

    Bảng lead đặt cọc chặn cùng lý do, nhưng hậu quả nặng hơn một bậc: tool đó
    GHI chứ không chỉ đọc. Một test lỡ chạm vào là chèn khách ma vào danh sách
    đội sale gọi thật.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from src.data.stores.dat_coc_db import DatCocDB
    from src.data.stores.inventory_db import InventoryDB

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db = InventoryDB("sqlite:///:memory:", engine=engine)
    db.ensure_table()
    for module in ("src.agents.tools.inventory", "src.agents.tools.search"):
        monkeypatch.setattr(f"{module}.get_inventory_db", lambda: db)

    engine_coc = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db_coc = DatCocDB("sqlite:///:memory:", engine=engine_coc)
    db_coc.ensure_table()
    # Vá ở CẢ HAI chỗ, khác với tồn kho phía trên. Vá mỗi module tool thì mới
    # chặn được đường gọi của tool; test nào `from src.data.stores.dat_coc_db
    # import get_dat_coc_db` để đọc lại kết quả vẫn bắn thẳng vào Supabase. Đã
    # xảy ra thật ngay khi viết test cho tool này: một dòng đọc lại danh sách
    # lead đã tạo bảng `dat_coc_lead` trên production.
    for muc_tieu in ("src.agents.tools.dat_coc", "src.data.stores.dat_coc_db"):
        monkeypatch.setattr(f"{muc_tieu}.get_dat_coc_db", lambda: db_coc)


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
