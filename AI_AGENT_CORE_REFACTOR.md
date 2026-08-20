# AI Agent Core Refactor Specification
## Real Estate Sales AI Agent — FastAPI + LangGraph + Supabase + Qdrant

> **Purpose:** This document is an implementation specification for Claude Code.
> The task is to refactor the **AI core/orchestration layer only** of the existing project.
> The existing frontend, deployed API contract, authentication, portal features, and UI must remain functional.

---

# 0. EXECUTIVE DECISION

## Target architecture

The system should evolve from the current deterministic LangGraph pipeline into a controlled hierarchical orchestration architecture:

```text
User
  |
  v
Context Loader
  |
  v
Fast Router / Query Understanding
  |       GPT-5.6 Luna
  |
  +-------------------+--------------------+
  |                   |                    |
  v                   v                    v
DIRECT              WORKFLOW             AGENT
  |                   |                    |
  |                   |                    v
  |                   |             Claude Sonnet 5
  |                   |              Orchestrator
  |                   |                    |
  |                   |              Tool Registry
  |                   |                    |
  |                   |        +-----------+-----------+
  |                   |        |           |           |
  |                   |        v           v           v
  |                   |    Supabase      Qdrant    Calculator
  |                   |
  +-------------------+--------------------+
                       |
                       v
                 Result Validator
                       |
                       v
                 Grounded Response
                       |
                       v
                      User
```

## Model allocation

### Primary recommendation

| Role | Model | Provider |
|---|---|---|
| Router / intent / structured extraction | `gpt-5.6-luna` | OpenAI |
| Simple response | `gpt-5.6-luna` | OpenAI |
| Main agent orchestrator | `claude-sonnet-5` | Anthropic |
| Complex multi-tool reasoning | `claude-sonnet-5` | Anthropic |
| Future difficult escalation | `claude-opus-4.8` or latest available Opus | Anthropic |
| Deterministic calculations | Python | No LLM |
| Embedding / retrieval | Existing embedding + Qdrant | No reasoning LLM |

### Why

The orchestrator is the most important model in this architecture. Claude Sonnet 5 is explicitly designed for highly agentic workloads, planning, tool use and autonomous multi-step execution. It is therefore the preferred model for the main Agent node.

OpenAI GPT-5.6 Luna is intended for cost-sensitive workloads and is suitable for high-volume routing, extraction and simpler responses.

**Do not use the flagship model for every request.**

---

# 1. CURRENT SYSTEM — DO NOT BREAK THIS

The existing backend is Python/FastAPI only.

## Service A — AI Core

```text
src/
Port: 8001
Role:
- Agent
- RAG
- LangGraph
- AI processing
```

Dependencies include:

```text
fastapi==0.141.1
langgraph==1.2.10
langchain-core==1.5.3
langchain-openai==1.4.1
```

## Service B — Product/API backend

```text
interface/backend/app/
Port: 8000
Role:
- authentication
- portal data
- product/API endpoints
- proxy SSE to AI Core
- AI_CORE_URL integration
```

Frontend:

```text
interface/frontend/
Vite + React 18
```

There is an old `.next/` directory, but it is NOT part of the running frontend architecture. Do not convert anything to Next.js.

---

# 2. CURRENT LANGGRAPH ARCHITECTURE

Current agent implementation:

```text
src/agents/graph.py
```

Uses:

```python
StateGraph
```

Current production behavior:

```text
router
  -> tools
  -> retrieve
  -> generate
  -> guardrail
```

The agent loop is currently disabled by:

```env
ENABLE_AGENT_LOOP=false
```

When enabled, the project has a plan/act loop.

## IMPORTANT

The current `/api/v1/chat/stream` path does NOT execute the graph directly.

The streaming endpoint manually executes nodes and uses:

```text
CONTEXT_NODES
```

from `graph.py` to preserve event ordering.

Therefore:

### DO NOT

- delete the existing streaming orchestration blindly
- assume changing `StateGraph` automatically changes SSE behavior
- duplicate business logic between stream and non-stream paths
- break existing SSE event names/contracts

### REQUIRED

Refactor shared node/business logic so both:

```text
non-stream graph
```

and:

```text
streaming execution
```

use the same underlying orchestration components.

The stream layer should become a thin presentation/execution adapter, not a second independent agent implementation.

---

# 3. DATA ARCHITECTURE

The project has TWO fundamentally different knowledge sources.

## 3.1 Supabase / PostgreSQL — Structured Property Data

Approximately 100 apartments are currently stored.

Example fields include:

```text
id
project
building
area
floor
bedrooms
bathrooms
direction
balcony_direction
area_m2
price
status
view
legal_status
...
```

The exact schema MUST be discovered from the existing code/database integration before implementation.

### Source of truth

Supabase/PostgreSQL is authoritative for:

- apartment ID
- apartment price
- apartment availability/status
- area
- floor
- bedroom count
- bathroom count
- direction
- balcony direction
- building/block
- apartment attributes
- structured property metadata

### IMPORTANT

Do NOT use Qdrant semantic search for structured apartment filtering.

Example:

> "Tìm căn 2PN dưới 5 tỷ, hướng Đông Nam, diện tích trên 65m²."

Correct:

```text
LLM extracts filters
       |
       v
Pydantic validation
       |
       v
Supabase query
       |
       v
property results
```

Incorrect:

```text
user
 -> embedding
 -> Qdrant
 -> guess property
```

---

# 4. QDRANT — UNSTRUCTURED PROJECT KNOWLEDGE

Qdrant currently contains vectorized textual knowledge such as:

```text
- Chính sách hỗ trợ lãi suất
- Chính sách bán hàng
- Tiện ích
- Tổng quan dự án
- Ưu đãi
- Vị trí
- Khoảng cách từ dự án tới nội đô
```

### Source of truth

Qdrant is authoritative for textual knowledge that is not naturally represented as apartment rows.

Examples:

```text
sales policy
financing policy
interest-rate support
promotions
amenities
project overview
location descriptions
distance/travel information
```

---

# 5. SOURCE-OF-TRUTH RULE

This rule is mandatory.

```text
Apartment price
        -> Supabase

Apartment availability
        -> Supabase

Apartment direction
        -> Supabase

Apartment area
        -> Supabase

Apartment attributes
        -> Supabase

Project policy
        -> Qdrant

Interest support policy
        -> Qdrant

Promotion
        -> Qdrant

Amenities
        -> Qdrant

Project overview
        -> Qdrant

Location information
        -> Qdrant
```

The LLM MUST NOT invent values when the authoritative source does not contain them.

If the system cannot find a reliable source:

```text
DO NOT GUESS
```

Instead:

```text
I could not find sufficiently reliable/current information to confirm this.
```

---

# 6. TARGET TOOL REGISTRY

Create a centralized tool registry.

Do not scatter tool definitions across unrelated graph nodes.

Recommended structure:

```text
src/
  agents/
    graph.py
    state.py
    router.py
    orchestrator.py
    tool_registry.py
    tool_executor.py
    validators.py
    prompts/
      router.md
      orchestrator.md
      response.md

  tools/
    property/
      search.py
      get.py
      compare.py

    knowledge/
      search.py

    finance/
      calculator.py

    ...
```

The exact directory structure may be adapted to the existing repository conventions.

---

# 7. CORE TOOLS

## 7.1 Property tools

### `search_properties`

Purpose:

Search apartments in Supabase using structured filters.

Example input:

```json
{
  "project": "Ocean Park",
  "bedrooms": 2,
  "price_max": 5000000000,
  "direction": "Đông Nam",
  "area_min": 65
}
```

Output:

```json
{
  "count": 3,
  "properties": [
    {
      "id": "A102",
      "price": 4800000000,
      "area_m2": 68,
      "direction": "Đông Nam"
    }
  ]
}
```

Requirements:

- Pydantic input schema
- parameter validation
- safe SQL/query construction
- no LLM inside the tool
- return structured data
- include property IDs
- preserve authoritative values

---

## 7.2 `get_property`

Retrieve complete details for one apartment.

Input:

```json
{
  "property_id": "A102"
}
```

---

## 7.3 `compare_properties`

Compare selected apartments.

Input:

```json
{
  "property_ids": ["A102", "A104", "A109"],
  "criteria": [
    "price",
    "area",
    "direction",
    "floor"
  ]
}
```

The comparison should be deterministic where possible.

---

# 8. QDRANT KNOWLEDGE TOOL

Create one reusable low-level retrieval tool:

```text
search_project_knowledge
```

Input:

```json
{
  "query": "Chính sách hỗ trợ lãi suất Ocean Park 2",
  "project": "Ocean Park 2",
  "category": "financing_policy",
  "top_k": 5
}
```

The exact metadata fields must be inspected from the existing Qdrant implementation.

Potential metadata:

```text
project
category
document_type
effective_date
source
page
document_id
```

Do NOT assume these fields already exist.

If metadata is not currently available, do not silently invent it. Document it as an optional ingestion improvement.

---

# 9. QDRANT RETRIEVAL STRATEGY

Preferred:

```text
Metadata filter
      |
      v
Candidate documents
      |
      v
Vector similarity
      |
      v
Top-K
```

For example:

```text
project = Ocean Park 2
category = financing_policy
```

then semantic search.

This is preferable to blindly searching the entire collection.

However:

### DO NOT rebuild the Qdrant ingestion pipeline unless necessary.

First inspect the current Qdrant schema and retrieval implementation.

Refactor retrieval only where it improves orchestration correctness.

---

# 10. FINANCE TOOLS

Calculations MUST be deterministic.

Examples:

```text
calculate_loan
calculate_monthly_payment
calculate_down_payment
calculate_cashflow
```

Example:

```json
{
  "principal": 2000000000,
  "annual_interest_rate": 8.5,
  "term_years": 20
}
```

The Python calculator returns the exact result.

LLM is responsible only for:

```text
extracting parameters
calling calculator
explaining the result
```

LLM must NOT perform the final financial arithmetic itself.

---

# 11. ROUTER

The router is a lightweight model call.

Recommended:

```text
GPT-5.6 Luna
```

Purpose:

- classify intent
- extract entities
- determine execution mode
- identify candidate capabilities
- decide whether the request needs agentic planning

The router does NOT answer the user.

Example:

```json
{
  "mode": "agent",
  "intent": "property_investment_consulting",
  "entities": {
    "project": "Ocean Park",
    "bedrooms": 2,
    "budget": 5000000000,
    "loan_amount": 2000000000
  },
  "required_capabilities": [
    "property_search",
    "financing_policy_search",
    "loan_calculator",
    "property_compare"
  ],
  "complexity": "high"
}
```

Use strict structured output/Pydantic validation.

---

# 12. EXECUTION MODES

There must be three execution modes.

## MODE A — DIRECT

For simple requests.

Example:

```text
"Ocean Park có những tiện ích gì?"
```

Flow:

```text
router
  -> knowledge search
  -> response
```

Do not invoke the main agent.

---

## MODE B — WORKFLOW

For deterministic multi-step tasks.

Example:

```text
"Tính khoản vay 2 tỷ trong 20 năm với lãi suất 8.5%."
```

Flow:

```text
router
  -> extract/validate
  -> calculator
  -> response
```

No autonomous agent loop.

---

## MODE C — AGENT

For complex multi-tool requests.

Example:

```text
"Khách có 5 tỷ, muốn mua căn 2PN Ocean Park 2 để đầu tư.
Có thể vay thêm 2 tỷ. Tìm căn phù hợp, xem chính sách lãi suất
và ưu đãi, tính khoản vay và đề xuất phương án tốt nhất."
```

Flow:

```text
router
  -> agent
  -> Claude Sonnet 5
  -> property search
  -> knowledge search
  -> loan calculator
  -> comparison
  -> synthesis
```

---

# 13. MAIN ORCHESTRATOR

Use:

```text
Claude Sonnet 5
```

API model ID:

```text
claude-sonnet-5
```

The orchestrator should be responsible for:

1. understanding the user's goal
2. identifying missing information
3. selecting tools
4. constructing tool arguments
5. evaluating tool results
6. deciding whether another tool call is needed
7. synthesizing grounded results
8. stopping when the task is complete

It should NOT:

- directly query the database
- directly access Qdrant internals
- perform business calculations
- fabricate missing facts
- bypass tool validation
- mutate production data without explicit authorization

---

# 14. AGENT STATE

Create/clean up a strongly typed LangGraph state.

Recommended fields:

```python
user_message
conversation_history

intent
mode
entities

property_filters
property_results

knowledge_queries
knowledge_results

calculations

tool_calls
tool_results
tool_history

sources
confidence

iteration_count
errors

final_answer
```

Use the existing state structure if compatible; do not create duplicate state objects unnecessarily.

---

# 15. LANGGRAPH TARGET GRAPH

The target non-stream graph should conceptually be:

```text
START
  |
  v
load_context
  |
  v
router
  |
  v
route_decision
  |
  +-------------------+
  |                   |
  v                   v
direct/workflow      agent
  |                   |
  |                   v
  |              orchestrator
  |                   |
  |                   v
  |              tool_executor
  |                   |
  |                   v
  |              result_validator
  |                   |
  |                   v
  |              agent_continue?
  |                /        \
  |              yes         no
  |               |           |
  |               +-----> orchestrator
  |                           |
  +---------------------------+
              |
              v
       response_generator
              |
              v
           guardrail
              |
              v
             END
```

The actual LangGraph implementation can differ if it improves correctness, but the responsibilities must remain separated.

---

# 16. AGENT LOOP POLICY

The current production setting is:

```env
ENABLE_AGENT_LOOP=false
```

Do NOT simply switch this to true.

Instead:

1. Keep backward compatibility.
2. Implement the new controlled agent path behind a feature flag.
3. Add maximum iteration count.
4. Add tool call limits.
5. Add timeout limits.
6. Add loop detection.

Recommended initial limits:

```text
MAX_AGENT_ITERATIONS = 5
MAX_TOOL_CALLS = 8
MAX_SAME_TOOL_REPEAT = 2
```

These should be configurable via environment variables.

---

# 17. TOOL EXECUTION POLICY

Every tool call should be logged internally:

```json
{
  "tool": "search_properties",
  "arguments": {
    "bedrooms": 2,
    "price_max": 5000000000
  },
  "duration_ms": 142,
  "success": true
}
```

Do not log API keys.

Do not log unnecessary sensitive customer data.

---

# 18. TOOL RISK LEVELS

Each tool should have metadata:

```json
{
  "name": "search_properties",
  "risk": "low",
  "requires_confirmation": false
}
```

Suggested categories:

```text
LOW
- property search
- Qdrant search
- property detail
- calculator

MEDIUM
- CRM read
- customer history

HIGH
- booking
- customer update
- sending messages
- changing records
```

High-risk tools require explicit confirmation before mutation.

---

# 19. RESULT VALIDATION

Add a validator after tool execution.

It should verify:

### Property result

```text
- property exists
- price came from Supabase
- required fields are valid
- no malformed result
```

### Knowledge result

```text
- content exists
- source exists when available
- relevance score is available when current implementation supports it
- metadata is preserved
```

### Calculator result

```text
- numeric inputs valid
- result numeric
- no NaN/infinite result
```

---

# 20. GROUNDING / ANTI-HALLUCINATION

The final response must be grounded in tool results.

Example:

```text
"Apartment A102 costs 4.8 billion VND."
```

must be traceable to:

```text
Supabase -> A102 -> price = 4.8B
```

Example:

```text
"The project currently supports X% interest for Y months."
```

must be traceable to:

```text
Qdrant -> financing policy document
```

If the source cannot be found:

```text
Do not invent.
```

---

# 21. RESPONSE GENERATION

Do not expose internal chain-of-thought.

The system may store concise execution metadata such as:

```text
tools_used
sources_used
confidence
```

but must never return hidden reasoning traces.

The user-facing response should contain:

- answer
- relevant property information
- calculations
- source references where available
- uncertainty when applicable

---

# 22. MULTI-AGENT POLICY

Do NOT implement true multi-agent architecture in the first refactor.

Do NOT create:

```text
Manager Agent
Property Agent
Finance Agent
Legal Agent
```

unless there is a demonstrated requirement.

For the current data scale and product scope:

```text
One Orchestrator
+
Specialized Tools
+
Deterministic Workflows
```

is preferred.

Future architecture can support specialist sub-agents through a common interface.

Example future interface:

```python
class SpecialistAgent(Protocol):
    async def run(task, context) -> SpecialistResult:
        ...
```

But this should NOT be required for the initial refactor.

---

# 23. FUTURE SPECIALIST AGENTS

If the system later needs them:

```text
Main Orchestrator
      |
      +-- Property Specialist
      +-- Investment Specialist
      +-- Finance Specialist
      +-- Legal Specialist
```

Preferred model initially:

```text
Claude Sonnet 5
```

Only create a specialist when:

- the domain has a genuinely complex workflow
- it needs independent planning
- it has many domain-specific tools
- evaluation shows one orchestrator is insufficient

---

# 24. MODEL ABSTRACTION

Do not hard-code provider-specific logic inside business nodes.

Create a model factory/registry.

Example conceptual configuration:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

OPENAI_ROUTER_MODEL=gpt-5.6-luna
OPENAI_SIMPLE_MODEL=gpt-5.6-luna
ANTHROPIC_ORCHESTRATOR_MODEL=claude-sonnet-5

ENABLE_NEW_ORCHESTRATOR=false
ENABLE_AGENT_LOOP=false
```

The exact environment variable names can be adapted to existing conventions.

Model selection must be centralized.

---

# 25. PROVIDER IMPLEMENTATION

The project currently has:

```text
langchain-openai
```

If using LangChain model abstractions for Anthropic, add the appropriate Anthropic integration dependency.

Preferred approach:

```text
LangGraph
  |
  +-- OpenAI chat model
  |
  +-- Anthropic chat model
```

Both should implement the same internal interface.

Do not duplicate agent logic for OpenAI and Anthropic.

The orchestrator should be provider-agnostic.

---

# 26. COST STRATEGY

Current API budget:

```text
OpenAI: approximately $5
Anthropic: approximately $5
```

Use these for development/evaluation efficiently.

Recommended allocation:

```text
GPT-5.6 Luna
    -> high-volume router/extraction/simple tasks

Claude Sonnet 5
    -> complex agentic orchestration
```

As of the current implementation date, OpenAI positions GPT-5.6 Luna for cost-sensitive workloads.

Anthropic positions Sonnet 5 as its most agentic Sonnet model and recommends it for production agents where advanced capability and cost efficiency need to be balanced.

Do NOT automatically use Opus for every agent request.

Add future escalation support, but keep it disabled initially.

---

# 27. PROMPT ARCHITECTURE

Separate prompts by responsibility.

```text
prompts/
  router.md
  orchestrator.md
  response.md
  guardrail.md
```

Do not create one enormous system prompt containing:

- all property data
- all policy documents
- all tools
- all business rules
- all response instructions

The model should retrieve information through tools.

---

# 28. ORCHESTRATOR SYSTEM RULES

The orchestrator should follow rules equivalent to:

```text
1. You are the planning/execution layer for a real-estate sales assistant.

2. Never invent property facts.

3. Property facts must come from property tools.

4. Policy/promotion/amenity facts must come from knowledge tools.

5. Financial calculations must come from deterministic calculator tools.

6. If a required fact is missing, search for it or state that it could not be verified.

7. Prefer the minimum number of tool calls required to solve the task.

8. Do not call a tool repeatedly with unchanged arguments.

9. Stop when the user request has been adequately satisfied.

10. Do not expose internal reasoning or hidden chain-of-thought.

11. Do not perform high-risk mutations without explicit confirmation.

12. Preserve source/provenance information.
```

---

# 29. EXAMPLE AGENT EXECUTION

User:

```text
Khách có 5 tỷ, muốn mua căn 2PN Ocean Park 2 để đầu tư.
Có thể vay thêm 2 tỷ. Tìm căn phù hợp, xem chính sách lãi suất
và ưu đãi hiện tại, tính khoản vay và đề xuất căn tốt nhất.
```

Expected:

```text
Router
  |
  +-- intent = investment_consulting
  +-- mode = agent
  +-- project = Ocean Park 2
  +-- bedrooms = 2
  +-- cash_budget = 5B
  +-- loan = 2B
```

Then:

```text
Orchestrator
  |
  +-- search_properties(...)
  |
  +-- search_project_knowledge(
        category="financing_policy"
      )
  |
  +-- search_project_knowledge(
        category="promotion"
      )
  |
  +-- calculate_loan(...)
  |
  +-- compare_properties(...)
  |
  +-- final synthesis
```

The final answer should distinguish:

```text
Property facts
-> Supabase

Policy facts
-> Qdrant

Financial result
-> calculator

Recommendation
-> LLM synthesis based on the above
```

---

# 30. STREAMING ARCHITECTURE

The existing streaming endpoint must continue to work.

Current behavior:

```text
/api/v1/chat/stream
```

manually executes nodes and emits SSE events.

Refactor it so that:

```text
shared orchestration logic
        |
        +---- non-stream LangGraph
        |
        +---- stream adapter
```

There must be only ONE source of truth for:

- routing
- tool execution
- validation
- response generation

Do not maintain separate implementations.

---

# 31. BACKWARD COMPATIBILITY

The refactor must preserve:

- existing frontend
- existing API endpoints
- existing request schemas where possible
- existing response schemas where possible
- authentication
- product portal
- SSE behavior
- existing RAG data
- existing Supabase data
- existing Qdrant collection
- existing deployment structure

If an API contract must change, create an adapter rather than breaking the existing frontend.

---

# 32. IMPLEMENTATION PHASES

## Phase 0 — Repository audit

Before modifying code:

1. Read the entire relevant `src/` structure.
2. Inspect:
   - `src/agents/graph.py`
   - `src/bootstrap.py`
   - current state definitions
   - current router
   - current tools
   - current RAG/Qdrant code
   - current Supabase integration
   - current streaming endpoint
   - environment/config code
3. Identify duplicated logic.
4. Identify current tool schemas.
5. Identify current SSE event contracts.
6. Produce a short internal implementation plan.

DO NOT modify files during the audit.

---

## Phase 1 — Model abstraction

Implement provider-independent model construction.

Requirements:

```text
OpenAI
Anthropic
```

must be swappable via configuration.

Test both providers independently.

---

## Phase 2 — Tool Registry

Centralize tools.

Every tool should expose:

```text
name
description
input schema
risk level
confirmation requirement
timeout
call limit
executor
```

---

## Phase 3 — Property tool

Implement/normalize:

```text
search_properties
get_property
compare_properties
```

using Supabase as source of truth.

---

## Phase 4 — Knowledge tool

Implement/normalize:

```text
search_project_knowledge
```

using Qdrant.

Preserve current retrieval behavior unless there is a clear correctness issue.

---

## Phase 5 — Router

Implement:

```text
GPT-5.6 Luna
```

with structured output.

Add:

```text
mode
intent
entities
complexity
required_capabilities
```

---

## Phase 6 — Orchestrator

Implement:

```text
Claude Sonnet 5
```

with LangGraph.

Use controlled tool calling.

---

## Phase 7 — Validation

Add:

```text
tool result validation
grounding
source tracking
loop protection
```

---

## Phase 8 — Streaming integration

Refactor `/api/v1/chat/stream` to use shared orchestration logic.

Do not duplicate node business logic.

---

## Phase 9 — Feature flag rollout

Introduce:

```env
ENABLE_NEW_ORCHESTRATOR=false
```

Initially.

Test:

```text
old pipeline
vs
new pipeline
```

before enabling by default.

---

# 33. TEST MATRIX

Create automated tests for at least these categories.

## Direct

```text
"Ocean Park có tiện ích gì?"
```

Expected:

```text
Qdrant
```

---

## Property search

```text
"Tìm căn 2PN dưới 5 tỷ."
```

Expected:

```text
Supabase
```

---

## Property filtering

```text
"Tìm căn 2PN dưới 5 tỷ hướng Đông Nam diện tích trên 65m²."
```

Expected:

```text
Supabase structured filters
```

---

## Financing

```text
"Vay 2 tỷ trong 20 năm thì trả bao nhiêu mỗi tháng?"
```

Expected:

```text
calculator
```

---

## Multi-source

```text
"Tìm căn 2PN dưới 5 tỷ và xem có hỗ trợ lãi suất không."
```

Expected:

```text
Supabase + Qdrant
```

---

## Complex agent

```text
"Khách có 5 tỷ, vay thêm 2 tỷ, muốn đầu tư căn 2PN Ocean Park.
Tìm và đề xuất phương án tốt nhất."
```

Expected:

```text
agent
-> Supabase
-> Qdrant
-> calculator
-> synthesis
```

---

## Missing information

```text
"Hiện tại chính sách chiết khấu chính xác là bao nhiêu?"
```

If no authoritative current source exists:

```text
Do not hallucinate.
```

---

# 34. EVALUATION METRICS

Add instrumentation for:

```text
Router accuracy
Intent accuracy
Mode selection accuracy
Tool selection accuracy
Tool argument accuracy
Property retrieval precision
RAG retrieval quality
Grounded answer rate
Task success rate
Average tool calls
Agent iterations
Latency
Input tokens
Output tokens
Estimated cost
Error rate
```

At minimum, every production request should make it possible to inspect:

```text
request_id
mode
model(s) used
tools used
tool durations
total latency
success/failure
```

---

# 35. OBSERVABILITY

Use structured logs.

Example:

```json
{
  "request_id": "abc123",
  "mode": "agent",
  "router_model": "gpt-5.6-luna",
  "orchestrator_model": "claude-sonnet-5",
  "tools": [
    "search_properties",
    "search_project_knowledge",
    "calculate_loan"
  ],
  "iterations": 3,
  "latency_ms": 4200,
  "success": true
}
```

Never log:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
passwords
JWT secrets
unnecessary PII
```

---

# 36. IMPORTANT NON-GOALS

Do NOT:

- rewrite the frontend
- migrate to Node.js
- migrate to Next.js
- replace FastAPI
- replace Supabase
- replace Qdrant
- replace LangGraph
- rebuild the entire RAG ingestion pipeline
- create multi-agent architecture prematurely
- delete existing working endpoints
- disable streaming
- remove authentication
- hard-code API keys
- put all data into the LLM prompt

---

# 37. DEFINITION OF DONE

The refactor is complete only when:

### Architecture

- [ ] Model abstraction exists
- [ ] Router exists
- [ ] Tool registry exists
- [ ] Controlled orchestrator exists
- [ ] Agent state is typed
- [ ] Validator exists
- [ ] Source/provenance is preserved

### Data

- [ ] Supabase is used for structured apartment search
- [ ] Qdrant is used for textual knowledge
- [ ] Calculator handles deterministic financial calculations

### Models

- [ ] GPT-5.6 Luna is configurable for router/simple tasks
- [ ] Claude Sonnet 5 is configurable for orchestrator
- [ ] Provider selection is not hard-coded into business logic

### LangGraph

- [ ] Non-stream graph works
- [ ] Agent loop is controlled
- [ ] Iteration limit exists
- [ ] Tool call limit exists
- [ ] Loop protection exists

### Streaming

- [ ] `/api/v1/chat/stream` still works
- [ ] Existing SSE contract is preserved
- [ ] Streaming does not contain duplicated business logic

### Safety

- [ ] No hallucinated property facts
- [ ] No hallucinated policies
- [ ] No LLM arithmetic for final financial calculations
- [ ] High-risk actions require confirmation

### Regression

- [ ] Existing API tests pass
- [ ] Existing frontend remains functional
- [ ] Existing auth remains functional
- [ ] Existing RAG remains functional
- [ ] Existing Supabase integration remains functional
- [ ] Existing Qdrant integration remains functional

---

# 38. CLAUDE CODE OPERATING INSTRUCTIONS

Claude Code MUST follow this order:

```text
1. INSPECT
2. UNDERSTAND
3. PLAN
4. IMPLEMENT
5. TEST
6. REGRESSION TEST
7. REPORT
```

### Critical rule

Do NOT immediately rewrite `src/agents/graph.py`.

First inspect:

```text
graph.py
bootstrap.py
state
router
tools
RAG
Qdrant
Supabase
streaming
config
tests
```

Then determine the smallest safe refactor.

### Preserve working behavior

The goal is:

```text
REFactor core AI architecture
NOT
REWRITE THE APPLICATION
```

Prefer incremental changes.

---

# 39. FINAL TARGET

The final architecture should conceptually be:

```text
                        ┌──────────────────────┐
                        │       FastAPI        │
                        │      AI Core :8001   │
                        └──────────┬───────────┘
                                   │
                                   v
                         ┌──────────────────┐
                         │ Context Manager  │
                         └────────┬─────────┘
                                  │
                                  v
                         ┌──────────────────┐
                         │ GPT-5.6 Luna     │
                         │ Router           │
                         └────────┬─────────┘
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
             v                    v                    v
          DIRECT              WORKFLOW              AGENT
             │                    │                    │
             │                    │                    v
             │                    │             Claude Sonnet 5
             │                    │               Orchestrator
             │                    │                    │
             │                    │             Tool Registry
             │                    │                    │
             │                    │       ┌────────────┼────────────┐
             │                    │       │            │            │
             │                    │       v            v            v
             │                    │   Supabase       Qdrant     Calculator
             │                    │       │            │            │
             └────────────────────┴───────┴────────────┴────────────┘
                                          │
                                          v
                                  Result Validator
                                          │
                                          v
                                  Response Generator
                                          │
                                          v
                                     Guardrail
                                          │
                                          v
                                        User
```

The central principle is:

> **Use LLMs for understanding, planning and synthesis. Use databases/tools for facts and deterministic operations. Use LangGraph for controlled orchestration.**

---

# 40. IMPLEMENTATION NOTE ON CURRENT MODEL PRICING

At the time this specification is written:

### OpenAI

OpenAI positions GPT-5.6 Luna as the cost-sensitive GPT-5.6 variant.

### Anthropic

Claude Sonnet 5 is the current recommended Sonnet-class model for agentic applications. It is currently offered at introductory API pricing through August 31, 2026, after which standard pricing applies.

The model names MUST remain configurable. Do not assume these exact model IDs will remain unchanged forever.

When the provider changes a model ID, update configuration rather than rewriting the architecture.
