"""Module AI_CORE — agent, node, tool, prompt.

Chủ sở hữu: viet

Cấu trúc:
    contracts.py      Protocol AgentService/LLMProvider + AgentTool (đóng băng)
    state.py          AgentState (TypedDict) + Intent
    graph.py          Dựng LangGraph state machine
    service.py        Facade cho tầng API (answer / stream)
    nodes/            base · router · retrieve · generate · guardrail
    tools/            registry · inventory (mock)
    prompts/          Prompt có version

Tầng API chỉ import src.agents.contracts.AgentService.
"""

from src.agents.contracts import (
    AgentService,
    AgentTool,
    LLMProvider,
    LLMTurn,
    OrchestratorMessage,
    ToolCall,
    ToolCallingProvider,
    ToolCallOutput,
    ToolResult,
)
from src.agents.state import AgentState, Intent, initial_state

__all__ = [
    "AgentService",
    "AgentState",
    "AgentTool",
    "Intent",
    "LLMProvider",
    "LLMTurn",
    "OrchestratorMessage",
    "ToolCall",
    "ToolCallOutput",
    "ToolCallingProvider",
    "ToolResult",
    "initial_state",
]
