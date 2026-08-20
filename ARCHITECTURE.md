# Architecture Document

## System Overview

[Tóm tắt 2-3 câu về kiến trúc hệ thống]

## Architecture Diagram

```mermaid
graph TB
    subgraph Frontend
        UI[React/Next.js UI]
    end

    subgraph Backend[FastAPI Backend]
        API[API Routes]
        Agent[LangGraph Agent]
        LLM[LLM Service]
        Tools[Agent Tools]
    end

    subgraph Data[Data Layer]
        DB[(Database)]
        Vector[Vector Store]
    end

    UI -->|HTTP/REST| API
    API --> Agent
    Agent --> LLM
    Agent --> Tools
    Agent --> Vector
    Tools --> DB
    API --> DB
```

## Components

### 1. Frontend (React/Next.js)
- **Purpose:** [mô tả]
- **Key Features:** [danh sách]
- **State Management:** [approach]

### 2. Backend (FastAPI)
- **Purpose:** [mô tả]
- **API Design:** RESTful
- **Authentication:** [JWT/None]

### 3. AI Agent (LangGraph)

> ⚠️ Phần còn lại của file này vẫn là **khung mẫu chưa điền**. Tài liệu kiến
> trúc THẬT, bám code đang chạy:
>
> - Toàn cảnh 3 service — [`docs/architecture_diagram.md`](docs/architecture_diagram.md)
> - Lõi AI (`src/`) — [`docs/kien-truc-loi-ai.md`](docs/kien-truc-loi-ai.md)
> - Quy ước làm việc — [`CLAUDE.md`](CLAUDE.md)

- **Agent Type:** state machine LangGraph, có cổng leo thang sang vòng lặp tool calling
- **Nodes:** `router` · `tools` · `retrieve` · `orchestrate` · `generate` · `guardrail`
- **Tools:** `inventory_lookup` · `inventory_search` · `inventory_summary` · `so_sanh_can` · `tinh_khoan_vay` · `dat_coc`
- **Flow:**

```mermaid
graph LR
    START --> A[Node A]
    A --> B{Decision}
    B -->|Yes| C[Node C]
    B -->|No| D[Node D]
    C --> E[END]
    D --> E
```

### 4. Database Supabase
- **Type:** [PostgreSQL / SQLite]
- **Tables:** [danh sách]
- **Migrations:** Alembic

### 5. Vector Store
- **Type:** [ChromaDB / FAISS / Pinecone]
- **Embeddings:** [model]
- **Purpose:** [RAG / similarity search]

## Data Flow

1. User gửi request từ Frontend
2. API route nhận và validate input
3. Agent xử lý qua LangGraph pipeline
4. LLM generate response
5. Tools thực thi actions (nếu cần)
6. Response trả về Frontend

## Deployment Architecture

```mermaid
graph LR
    subgraph Docker
        FE[Frontend Container]
        BE[Backend Container]
        DB_C[Database Container]
    end
    FE --> BE --> DB_C
```

## Security

- API keys stored in `.env` (never commit)
- Input validation via Pydantic
- Rate limiting on API endpoints
- CORS configured for frontend domain

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Framework | FastAPI | Async, auto-docs, type-safe |
| Agent | LangGraph | Flexible state management |
| Database | [choice] | [reason] |
| Frontend | Next.js | [reason] |
