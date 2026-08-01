"""Dependency injection cho FastAPI.

Router không tự khởi tạo dịch vụ — luôn nhận qua Depends. Nhờ vậy test ghi đè
được bằng app.dependency_overrides mà không phải patch lung tung.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.agents.contracts import AgentService
from src.core.config import Settings, get_settings
from src.core.container import container
from src.services.portal import PortalRepository


def get_agent_service() -> AgentService:
    return container.resolve(AgentService)


def get_portal_repository() -> PortalRepository:
    return container.resolve(PortalRepository)


SettingsDep = Annotated[Settings, Depends(get_settings)]
AgentDep = Annotated[AgentService, Depends(get_agent_service)]
PortalDep = Annotated[PortalRepository, Depends(get_portal_repository)]
