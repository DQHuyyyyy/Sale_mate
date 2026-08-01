# Kientruc.md — Kiến trúc hệ thống

## 1. Tổng quan 4 tầng

```
┌─ CLIENT ──────────────────────────────────────────────┐
│  Sale (chat, mobile-first web)   Admin (upload/quản trị)│
└───────────────┬───────────────────────┬───────────────┘
                ▼                       ▼
┌─ BACKEND (FastAPI) ───────────────────────────────────┐
│  Auth & RBAC   │  Agent orchestrator │ Ingestion       │
│                │  router·grounding·  │ parse·chunk·    │
│                │  HITL               │ embed           │
└──────┬─────────────────┬───────────────────┬──────────┘
       ▼                 ▼                   ▼
┌─ DỮ LIỆU & TOOL ──────────────────────────────────────┐
│ Qdrant (vector+meta) │ Postgres      │ Inventory API   │
│                      │ user·giá·log  │ (realtime)      │
│                      │               │ + Re-ranker     │
└──────────────────────────────┬───────────────────────┘
                               ▼
                    ┌─ LLM (Claude / GPT-4o) ─┐
                    │ sinh câu trả lời có nguồn │
                    └──────────────────────────┘
```

## 2. Thành phần & trách nhiệm

- **Client (Next.js)**: hai giao diện trên cùng codebase — Sale chat và Admin console. Mobile-first web. Xem `Giaodien.md`.
- **Auth & RBAC (FastAPI)**: cấp JWT, gắn vai trò vào request. Vai trò quyết định `visibility` được truy hồi.
- **Agent orchestrator**: bộ não — router, retrieve, tool, grounding, HITL. Xem `Core.md`.
- **Ingestion pipeline**: nhận file admin, parse (bảng/ảnh), chunk, embed, ghi Qdrant + đăng ký version vào Postgres.
- **Qdrant**: vector + metadata; payload filtering phục vụ phân quyền.
- **Postgres**: dữ liệu có cấu trúc (user, bảng giá, tồn kho cache, tài liệu/version, lịch sử chat, log hành động nhạy cảm).
- **Inventory API**: nguồn tồn kho realtime (thật hoặc mock ở giai đoạn đầu).
- **Re-ranker**: xếp lại top-k trước khi vào LLM.
- **LLM**: sinh câu trả lời cuối; model rẻ cho router/phân loại.

## 3. Hai luồng dữ liệu

**Ingest (ghi):** admin upload → parse → tách bảng giá sang Postgres, văn bản chunk → embed → Qdrant (kèm metadata + version) → đăng ký documents/version vào Postgres.

**Query (đọc):** câu hỏi → auth gắn vai trò → router → retrieve Qdrant (đã lọc theo quyền + is_active) → rerank → (nếu cần) tool tồn kho/giá → LLM grounding + citation → nếu nhạy cảm → cổng HITL → stream về client.

## 4. Non-functional

- **Độ trễ**: mục tiêu phản hồi < vài giây tại hiện trường. Biện pháp: streaming, prompt caching, model rẻ cho router, hạn chế số vòng agent.
- **Độ tươi**: tồn kho không cache lâu; tài liệu mới re-index kịp thời.
- **Chi phí**: theo dõi token/câu; tách model theo tác vụ.
- **Quan sát**: tracing toàn pipeline (Langfuse/Phoenix).
- **Bảo mật**: chống prompt injection (tài liệu là dữ liệu, không phải lệnh); không rò rỉ tài liệu nội bộ; không log dữ liệu nhạy cảm.

## 5. Môi trường & deploy

- **Local**: `docker-compose` chạy Postgres + Qdrant; BE `uvicorn`, FE `next dev`.
- **Staging/Prod**: FE trên **Vercel**; BE trên **Fly.io**; Qdrant + Postgres dùng cloud hoặc self-host trên Fly.
- **Secrets**: qua biến môi trường / secrets manager của Fly & Vercel. Không commit key.
- **CI**: lint + test chạy trên mỗi PR.

## 6. Quyết định kiến trúc đã chốt (ghi lại lý do)

- **Qdrant thay vì Weaviate**: self-host đơn giản, payload filtering mạnh cho phân quyền.
- **Bảng giá vào Postgres, không vào RAG**: đảm bảo giá/diện tích chính xác.
- **Tồn kho qua tool, không vào vector DB**: dữ liệu realtime, RAG luôn là bản chụp cũ.
- **BGE-M3 / e5 cho tiếng Việt**: embedding phổ thông yếu tiếng Việt, ảnh hưởng trực tiếp độ chính xác.
