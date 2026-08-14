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
| Frontend | Vite · React 18 · React Router (`interface/frontend/`) |
| API sản phẩm | FastAPI · Pydantic v2 · Python 3.11 (`interface/backend/`, :8000) |
| Lõi AI | FastAPI (`src/`, :8001) — API sản phẩm gọi vào qua `AI_CORE_URL` |
| Agent | LangGraph — router · tools · retrieve · generate · guardrail |
| Vector store | Qdrant (payload filtering cho phân quyền) |
| Embedding | OpenAI `text-embedding-3-small` → BGE-M3 |
| LLM | Hai tầng: model rẻ cho router, model mạnh cho câu trả lời |
| Database | PostgreSQL |
| DevOps | Docker multi-stage · GitHub Actions · Render + Vercel |

Lý do đằng sau từng lựa chọn: [`docs/adr/`](docs/adr/README.md).

---

## Chạy thử

Hệ thống gồm **3 service chạy song song** trong 3 terminal riêng, cộng hạ tầng
Qdrant/Postgres — xem chi tiết ở [`RUN.md`](RUN.md). Sơ đồ đầy đủ:
[`docs/architecture_diagram.md`](docs/architecture_diagram.md).

### Yêu cầu

- **Python 3.11** (bắt buộc — khớp CI và Dockerfile)
- **Node.js 20+**
- Docker (tuỳ chọn — chỉ cần khi dùng Qdrant/Postgres thật; mặc định hệ thống
  dùng vector store trong bộ nhớ nên **không bắt buộc** để dev)

### 0. Cài đặt một lần

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

make install                       # dependencies lõi AI (src/)
make install-api                   # dependencies API sản phẩm (interface/backend/)
make install-fe                    # dependencies frontend (interface/frontend/)

cp .env.example .env               # rồi điền OPENAI_API_KEY, JWT_SECRET...
```

Cả `interface/backend` và `src/` đọc **chung một file `.env`** ở gốc repo —
không tạo `.env` riêng cho từng service. Danh sách đầy đủ biến môi trường (LLM,
Qdrant, Supabase, `JWT_SECRET`, `AI_CORE_URL`...) đã có sẵn trong
[`.env.example`](.env.example) kèm chú thích lấy ở đâu.

### 1. Chạy — 3 terminal

```bash
# Terminal 1 — lõi AI (agent + RAG)
make run-ai                        # http://localhost:8001/docs

# Terminal 2 — API sản phẩm (auth, tồn kho, khu/toà...)
make run-api                       # http://localhost:8000/docs

# Terminal 3 — frontend
make fe                            # http://localhost:5173
```

Mở `http://localhost:5173`, chat qua widget góc dưới phải. Frontend gọi
`/api/*` → Vite proxy sang `:8000` (API sản phẩm) → cầu `/api/chat` gọi tiếp
sang `:8001` (lõi AI) qua `AI_CORE_URL`. Chưa có `OPENAI_API_KEY` hợp lệ thì lõi
AI **vẫn chạy**: tự rơi về LLM giả lập, widget vẫn stream chữ — chỉ là nội
dung mẫu.

### 2. Hạ tầng (tuỳ chọn)

```bash
make infra          # Qdrant :6333 + Postgres :5432
make infra-down
```

### 3. Nạp dữ liệu RAG vào Qdrant (tuỳ chọn)

Qdrant (local hoặc Cloud — xem `QDRANT_URL`/`QDRANT_API_KEY` trong `.env`) lúc
mới bật là **rỗng**. `git pull` chỉ lấy code, không lấy dữ liệu — mỗi máy phải
tự nạp.

Mọi thao tác dữ liệu đi qua **một dòng lệnh duy nhất**:

```bash
python -m src.cli status                 # vector store đang có gì
python -m src.cli ingest --all           # nạp cả 4 nguồn
python -m src.cli ingest inventory       # nạp một nguồn
python -m src.cli search "câu hỏi"       # thử truy hồi
python -m src.cli eval retrieval         # đo trên bộ câu hỏi vàng
```

| Nguồn | Nội dung | Quyền | Cần gì |
|---|---|---|---|
| `meeyland` | Tin đăng meeyland.com | public | Chạy được ngay — crawl thẳng từ web |
| `inventory` | Tồn kho 100 căn (CSV) | internal | `data/raw/inventory.csv` |
| `batdongsan` | Tin batdongsan.com.vn lưu tay | public | `data/raw/*.html` |
| `knowledge` | Chính sách · pháp lý · tiện ích | tuỳ file | `data/raw/knowledge/**.md` |

`data/raw/` nằm trong `.gitignore` nên **không có trong repo** — xin Viet qua
Drive trước khi chạy ba nguồn cuối. File `.md` bắt buộc có front-matter
`title`/`section`/`visibility` ở đầu; xem `src/data/sources/knowledge_docs.py`.

> Nạp dữ liệu **bắt buộc có `OPENAI_API_KEY` hợp lệ**. Trước đây script tự rơi
> về embedding giả lập khi thiếu key — vector 64 chiều ghi vào collection 1536
> chiều, hỏng dữ liệu. Nay thiếu key là dừng ngay với thông báo rõ ràng.

---

## Lệnh hay dùng

| Lệnh | Việc |
|---|---|
| `make run-ai` | Chạy lõi AI (:8001) |
| `make run-api` | Chạy API sản phẩm (:8000) |
| `make fe` | Chạy frontend (:5173) |
| `make test` | Test lõi AI (`tests/`) |
| `make test-api` | Test API sản phẩm (`interface/backend/tests/`) |
| `make cov` | Test lõi AI kèm báo cáo coverage |
| `make check` | lint + format + test cho `src/` — **chạy trước khi push** |
| `make check-all` | `check` + `test-api` |
| `make infra` | Bật Qdrant + Postgres |
| `make data-status` / `data-ingest` / `data-eval` | Xem/nạp/đo dữ liệu RAG |

---

## API

Frontend chỉ gọi **API sản phẩm** (`:8000`); API sản phẩm mới là bên gọi tiếp
sang lõi AI (`:8001`) qua `AI_CORE_URL` — xem sơ đồ ở mục Chạy thử.

**API sản phẩm** (`interface/backend/`) — tài liệu tương tác: `http://localhost:8000/docs`

| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/api/auth/login` | Đăng nhập, trả JWT |
| `GET` | `/api/auth/me` | Thông tin user hiện tại |
| `GET` | `/api/apartments` | Danh sách căn hộ |
| `GET` | `/api/apartments/{ma_can}` | Chi tiết một căn |
| `GET` | `/api/zones` · `/api/towers` | Khu / toà |
| `GET`/`POST` | `/api/sales` | Lịch sử bán |
| `GET`/`POST` | `/api/documents` | Tài liệu |
| `POST` | `/api/chat` · `/api/chat/stream` | Cầu nối chat — gọi tiếp sang lõi AI |

**Lõi AI** (`src/`) — tài liệu tương tác: `http://localhost:8001/docs`

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/health` | Health check ở gốc (Docker, uptime monitor) |
| `GET` | `/api/v1/health` | Health check chi tiết kèm trạng thái từng thành phần |
| `POST` | `/api/v1/chat` | Hỏi trợ lý, trả lời một lần |
| `POST` | `/api/v1/chat/stream` | Hỏi trợ lý, **stream SSE** |

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

## Câu hỏi mẫu

Gõ thẳng vào widget chat (`http://localhost:5173`, sau khi đã nạp dữ liệu ở
mục "Nạp dữ liệu RAG"). Các câu dưới lấy từ bộ kiểm thử thật ở
[`eval/golden_dataset.json`](eval/golden_dataset.json), agent trả lời có trích
nguồn:

- "Căn hộ VOP398 tại tòa R103 có giá bán bao nhiêu tiền?"
- "Tìm căn hộ 2 phòng ngủ giá từ 3.0 tỷ đến 3.6 tỷ tại tòa S2"
- "Dự án Vinhomes Ocean Park có những tiện ích nội khu nổi bật nào?"
- "Phí gửi ô tô hàng tháng ở khu Sapphire là bao nhiêu?"
- "Chính sách bán hàng và tiến độ thanh toán dự án OCP2 (The Empire) thế nào?"

Câu hỏi ngoài phạm vi dữ liệu (ví dụ "lãi suất vay ngân hàng bao nhiêu") sẽ bị
guardrail từ chối đúng thay vì bịa số — đây là hành vi **mong muốn**, không
phải lỗi.

---

## Cấu trúc thư mục

```
P-055/
├── src/                LÕI AI — FastAPI riêng, cổng 8001
│   ├── core/           config · logging · exceptions · DI container
│   ├── models/         DTO — HỢP ĐỒNG FE ↔ BE (đóng băng)
│   ├── data/           RAG: contracts · ingestion · stores · retrieval
│   ├── agents/         AI core: graph · nodes · tools · prompts
│   ├── api/            HTTP: deps · errors · v1/ (chat, health)
│   ├── services/       Adapter ra ngoài: OpenAI
│   ├── bootstrap.py    NƠI DUY NHẤT gắn interface ↔ implementation
│   └── main.py         FastAPI app — lõi AI
├── interface/
│   ├── frontend/       Vite + React — portal + AIWidget, cổng 5173
│   └── backend/        API SẢN PHẨM riêng — FastAPI, cổng 8000
│                        auth · apartments · zones · sales · users · documents
│                        chat/ gọi tiếp sang src/ qua AI_CORE_URL
├── tests/               test lõi AI, không test nào gọi mạng
├── docs/
│   ├── adr/            Architecture Decision Records
│   ├── architecture_diagram.md
│   └── guide/           Guidebook 10 chương của BTC
├── eval/                Bằng chứng đánh giá
└── presentation/        Pitch deck · video demo
```

Nguyên tắc: mỗi module chỉ import `contracts.py` và `models/` của module khác,
không bao giờ import class cụ thể. Nhờ vậy bốn người làm song song mà không chặn
nhau — xem [ADR-004](docs/adr/ADR-004-module-contracts.md).

---

## Chất lượng

- **240 test** lõi AI (`tests/`) + **38 test** API sản phẩm
  (`interface/backend/tests/`) pass, **coverage 77%** (mục tiêu tối thiểu 60%)
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
| [`RUN.md`](RUN.md) | Chạy trên máy mình |
| [`DEPLOY.md`](DEPLOY.md) | Đưa lên Vercel + Render, hai môi trường, chi phí 0đ |
| [`docs/architecture_diagram.md`](docs/architecture_diagram.md) | Sơ đồ kiến trúc, luồng agent, luồng dữ liệu |
| [`docs/adr/`](docs/adr/README.md) | Quyết định kiến trúc và lý do |
| [`Context Product/`](Context%20Product/) | Đặc tả sản phẩm: giao diện · lõi AI · data · API |
| [`docs/guide/`](docs/guide/) | Guidebook 10 chương của BTC |
| [`JOURNAL.md`](JOURNAL.md) | Nhật ký phát triển theo tuần |
| [`WORKLOG.md`](WORKLOG.md) | Nhật ký công việc hàng ngày |
