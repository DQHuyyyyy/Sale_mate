# SalesMate — Nền tảng bất động sản xác thực

> Cổng thông tin bất động sản có xác thực pháp lý · quy hoạch · giá, kèm **trợ
> lý AI** dạng widget nổi tư vấn giá, tìm bất động sản, giải đáp pháp lý và soạn
> tin đăng.

**Team P-055** · VinUni AI20K Build Phase — Cohort 3

---

## Vấn đề

Người mua bất động sản ở Việt Nam ra quyết định trên thông tin không kiểm chứng
được: tin đăng sai giá, pháp lý mập mờ, quy hoạch không rõ. Người bán và môi
giới thì mất thời gian trả lời đi trả lại cùng một nhóm câu hỏi.

## Giải pháp

Một portal mà **mỗi tin đăng đều mang dấu xác thực**, cộng một trợ lý AI trả lời
câu hỏi ngay trên trang — và quan trọng hơn: **biết dừng khi không đủ dữ liệu**
thay vì bịa ra số.

Ba nguyên tắc chi phối toàn bộ thiết kế:

1. **Không bịa số.** Giá, diện tích, tình trạng căn chỉ được nêu khi có trong
   tài liệu hoặc kết quả tra cứu.
2. **Luôn trích nguồn.** Mọi khẳng định lấy từ tài liệu đều kèm tên tài liệu và
   phiên bản.
3. **Phân quyền lọc tại tầng truy hồi**, không lọc ở giao diện — tài liệu nội bộ
   không bao giờ lọt vào ngữ cảnh của LLM.

---

## Tech stack

| Lớp | Công nghệ |
|---|---|
| Frontend | Next.js 16 (App Router) · TypeScript · Tailwind v4 |
| Backend | FastAPI · Pydantic v2 · Python 3.11 |
| Agent | LangGraph — router · retrieve · generate · guardrail |
| Vector store | Qdrant (payload filtering cho phân quyền) |
| Embedding | OpenAI `text-embedding-3-small` → BGE-M3 |
| LLM | Hai tầng: model rẻ cho router, model mạnh cho câu trả lời |
| Database | PostgreSQL |
| DevOps | Docker multi-stage · GitHub Actions · Render + Vercel |

Lý do đằng sau từng lựa chọn: [`docs/adr/`](docs/adr/README.md).

---

## Chạy thử

### Yêu cầu

- **Python 3.11** (bắt buộc — khớp CI và Dockerfile)
- **Node.js 20+**
- Docker (tuỳ chọn — chỉ cần khi dùng Qdrant/Postgres thật)

### 1. Backend

```bash
# Tạo môi trường ảo bằng Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env               # rồi điền OPENAI_API_KEY

make run                           # http://localhost:8000/docs
```

Chưa có `OPENAI_API_KEY` hợp lệ thì hệ thống **vẫn chạy**: nó tự rơi về LLM giả
lập, widget vẫn stream chữ — chỉ là nội dung mẫu.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                        # http://localhost:3000
```

### 3. Hạ tầng (tuỳ chọn)

```bash
make infra          # Qdrant :6333 + Postgres :5432
make infra-down
```

Mặc định hệ thống dùng vector store trong bộ nhớ nên **không cần Docker** để dev.

### 4. Nạp dữ liệu RAG thật vào Qdrant (tuỳ chọn)

Qdrant (local hoặc Cloud — xem `QDRANT_URL`/`QDRANT_API_KEY` trong `.env`) lúc
mới bật là **rỗng** — mỗi máy phải tự nạp dữ liệu, `git pull` code không tự có
sẵn data. Có 4 nguồn, chạy theo thứ tự:

```bash
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_inventory.py       # tồn kho căn hộ (CSV + ảnh) — internal
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_batdongsan.py      # tin batdongsan.com.vn (lưu tay) — public
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_more_sources.py    # tin meeyland.com (crawl trực tiếp) — public
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_knowledge_docs.py  # chính sách/pháp lý/tiện ích (.md) — internal hoặc public tuỳ file
```

`ingest_more_sources.py` (meeyland) crawl thẳng từ web nên chạy được ngay, không
cần gì thêm. `ingest_inventory.py`/`ingest_batdongsan.py` đọc file trong
`data/raw/` — thư mục này nằm trong `.gitignore` nên **không có trong repo**,
cần xin Viet file CSV/ảnh (Drive) và bộ HTML batdongsan đã lưu tay để bỏ vào
đúng chỗ trước khi chạy. `ingest_knowledge_docs.py` đọc file `.md` trong
`data/raw/knowledge/` (cũng gitignore) — mỗi file bắt buộc front-matter
`title`/`section`/`visibility: internal|public` ở đầu, xem
`src/data/sources/knowledge_docs.py` để biết định dạng.

---

## Lệnh hay dùng

| Lệnh | Việc |
|---|---|
| `make run` | Chạy backend |
| `make fe` | Chạy frontend |
| `make test` | Chạy test |
| `make cov` | Test kèm báo cáo coverage |
| `make check` | lint + format + test — **chạy trước khi push** |
| `make infra` | Bật Qdrant + Postgres |

---

## API

Tài liệu tương tác: `http://localhost:8000/docs`

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/health` | Health check ở gốc (Docker, uptime monitor) |
| `GET` | `/api/v1/health` | Health check chi tiết kèm trạng thái từng thành phần |
| `POST` | `/api/v1/chat` | Hỏi trợ lý, trả lời một lần |
| `POST` | `/api/v1/chat/stream` | Hỏi trợ lý, **stream SSE** |
| `GET` | `/api/v1/listings` | Tin đăng — lọc `?listing_type=sale\|rent\|transfer` |
| `GET` | `/api/v1/projects` | Dự án nổi bật |
| `GET` | `/api/v1/demands` | Nhu cầu người dùng đăng |
| `GET` | `/api/v1/market` | Thống kê thị trường trong ngày |

Lỗi luôn theo một khuôn dạng, thông điệp bằng tiếng Việt:

```json
{ "error": { "code": "llm_quota_exhausted", "message": "Tài khoản AI đã hết credit…" } }
```

### Sự kiện SSE

```
data: {"type":"start","session_id":"…"}
data: {"type":"token","content":"Chào "}
data: {"type":"done","session_id":"…"}
```

Đủ 6 loại: `start` · `route` · `token` · `sources` · `done` · `error`.

---

## Cấu trúc thư mục

```
P-055/
├── src/
│   ├── core/          config · logging · exceptions · DI container
│   ├── models/        DTO — HỢP ĐỒNG FE ↔ BE (đóng băng)
│   ├── data/          RAG: contracts · ingestion · stores · retrieval
│   ├── agents/        AI core: graph · nodes · tools · prompts
│   ├── api/           HTTP: deps · errors · v1/
│   ├── services/      Adapter ra ngoài: OpenAI · portal repo
│   ├── bootstrap.py   NƠI DUY NHẤT gắn interface ↔ implementation
│   └── main.py        FastAPI app
├── interface/         FE + API sản phẩm gộp một chỗ
│   ├── frontend/      Next.js — portal + AIWidget
│   └── backend/       API sản phẩm :8000 — auth · apartments · zones · sales
├── tests/             57 test, không test nào gọi mạng
├── docs/
│   ├── adr/           Architecture Decision Records
│   ├── architecture_diagram.md
│   └── guide/         Guidebook 10 chương của BTC
├── eval/              Bằng chứng đánh giá
└── presentation/      Pitch deck · video demo
```

Nguyên tắc: mỗi module chỉ import `contracts.py` và `models/` của module khác,
không bao giờ import class cụ thể. Nhờ vậy bốn người làm song song mà không chặn
nhau — xem [ADR-004](docs/adr/ADR-004-module-contracts.md).

---

## Chất lượng

- **57 test** pass, **coverage 81%** (mục tiêu tối thiểu 60%)
- **Ruff** lint + format sạch, chạy tự động trong CI
- CI chạy cả backend (lint · format · test · coverage gate) và frontend
  (lint · build) trên mỗi PR
- Không test nào gọi OpenAI hay Qdrant thật — dùng `FakeEmbedder`,
  `ScriptedProvider`, `InMemoryVectorStore`

```bash
make cov
```

---

## Team

| Thành viên | Phụ trách | Thư mục sở hữu |
|---|---|---|
| **huy** (lead) | Kiến trúc · Frontend | `interface/frontend/` · `src/core/` |
| **dat** | Data handling (RAG) | `src/data/` |
| **viet** | AI core (agent) | `src/agents/` |
| **phuc** | Interface (backend API) | `src/api/` |

Quy trình: nhánh cá nhân → PR vào `develop` → merge vào `main`.
Commit theo chuẩn `feat:` `fix:` `docs:` `test:` `refactor:`.

---

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Điểm vào cho cả team và AI coding assistant |
| [`docs/architecture_diagram.md`](docs/architecture_diagram.md) | Sơ đồ kiến trúc, luồng agent, luồng dữ liệu |
| [`docs/adr/`](docs/adr/README.md) | Quyết định kiến trúc và lý do |
| [`Context Product/`](Context%20Product/) | Đặc tả sản phẩm: giao diện · lõi AI · data · API |
| [`docs/guide/`](docs/guide/) | Guidebook 10 chương của BTC |
| [`JOURNAL.md`](JOURNAL.md) | Nhật ký phát triển theo tuần |
| [`WORKLOG.md`](WORKLOG.md) | Nhật ký công việc hàng ngày |
