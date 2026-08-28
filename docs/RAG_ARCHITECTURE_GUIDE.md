# Hướng Dẫn Kiến Trúc & Cách Chạy RAG Pipeline (SalesMate AI Core)

Tài liệu này tổng hợp toàn bộ hệ thống **RAG Pipeline (Retrieval-Augmented Generation)**, mối liên kết giữa dữ liệu thật tại thư mục `data/` với mã nguồn `src/data/`, và hướng dẫn chi tiết cách chạy từng thành phần.

---

## 📐 1. Mối Liên Kết Giữa Thư Mục `data/` và `src/data/`

Dự án phân tách rõ ràng giữa **Dữ liệu thật** và **Logic lập trình**:

```
                                  ┌────────────────────────────────────────┐
                                  │       FILE DỮ LIỆU THẬT: data/         │
                                  │ - data/raw/knowledge/ (11 tài liệu .md)│
                                  │   NGUỒN DUY NHẤT của Qdrant            │
                                  └───────────────────┬────────────────────┘
                                                      │
                                                      │ (src/cli.py ingest --all)
                                                      ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LOGIC XỬ LÝ & RAG: src/data/                                    │
│                                                                                                   │
│  1. Ingestion & Chunking     2. Hybrid Vector Search      3. Two-Stage Rerank      4. Generation   │
│ ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────┐  ┌───────────────┐ │
│ │ - parsers.py           │  │ - contracts.py         │  │ - rerankers.py     │  │ - generate.py │ │
│ │ - chunkers.py (900ch)  │─►│ - memory_store.py      │─►│   (Top-12 -> Top-3)  │─►│ - llm.py      │ │
│ │ - embedders.py         │  │ - qdrant_store.py      │  │ - retriever.py     │  │ - service.py  │ │
│ └────────────────────────┘  └────────────────────────┘  └────────────────────┘  └───────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Thư mục `data/raw/knowledge/` (Ngoài root)**: **11 tài liệu chính sách** dạng `.md` — nguồn duy nhất được ingest. Mỗi file một `doc_id = knowledge:{tên file}`, khớp một-đối-một với Qdrant.

  ⚠️ **Giá, diện tích và tình trạng căn KHÔNG nằm ở đây.** Chúng ở Postgres và tool đọc trực tiếp lúc hỏi — RAG luôn là bản chụp, còn giá đổi hàng ngày. Bản tài liệu trước mô tả `data/vop_listings.json` với 100+ căn; file đó **không còn tồn tại** và 871 chunk tin rao sinh ra từ nó đã bị xoá khỏi Qdrant.
- **Thư mục `src/data/` (Trong src)**: Nơi chứa **Mã nguồn thuật toán** (Code parser đọc file, code chunking, code tạo vector, code Qdrant store, code Cross-Encoder rerank).

---

## 🧩 2. Tổng Quan Các Thành Phần Đã Build Trong RAG

### 2.1. Ingestion & Data Handling (`src/data/ingestion/` & `src/data/parsers.py`)
- **Dữ liệu thô**: Parse từ `data/raw/knowledge/*.md`. Mỗi file bắt buộc có front-matter `title` / `section` / `visibility` **và** một heading H1 khớp `title` — thiếu là `load_knowledge_file` báo lỗi. (Đã có lần 10/10 file thiếu H1 nên kho không nạp lại được suốt một thời gian dài mà không ai biết.)
- **Metadata Schema**: Đóng gói đầy đủ các trường: `ma_can`, `price`, `area`, `num_bedrooms`, `building`, `doc_kind` (hiện **chỉ còn** `"policy"`), `image_url` (Link Ảnh căn hộ), `visibility` (`"public"` vs `"internal"`).
- **Chunking**: Sử dụng `SentenceChunker` tách đoạn ~900 ký tự, overlap 120 ký tự, giữ nguyên ranh giới câu.

### 2.2. Vector Search & Hybrid Filtering (`src/data/stores/` & `src/data/contracts.py`)
- **Lọc cứng cấu trúc (`RetrievalFilter`)**: Lọc theo khoảng giá (`min_price`, `max_price`), diện tích, số phòng ngủ, tòa, loại căn và quyền truy cập `visibility` ngay tại tầng truy vấn vector (trước khi rank).
- **VectorStore Supported**: `InMemoryVectorStore` (chạy trên RAM cho dev/test) và `QdrantVectorStore` (VectorDB sản phẩm cho staging/production).

### 2.3. Cross-Encoder Two-Stage Reranking (`src/data/retrieval/rerankers.py`)
- **Giai đoạn 1 (Candidate Retrieval)**: Lấy $top\_k = 12$ ứng viên từ Vector Search.
- **Giai đoạn 2 (Cross-Encoder Rerank)**: Sử dụng mô hình Cross-Encoder (`BAAI/bge-reranker-v2-m3` hoặc `FakeCrossEncoderReranker`) chấm điểm trực tiếp cặp `(query, chunk.text)` và chắt lọc lấy **$top\_n = 3$ tinh túy nhất** đưa vào Prompt.

### 2.4. Prompt Engineering & Grounding (`src/agents/prompts/` & `src/agents/nodes/generate.py`)
- **Rich Context (`as_context()`)**: Tự động ghép Top-3 chunks thành văn bản ngữ cảnh giàu thông tin:
  ```text
  Ma can: VOP398, Toa R103, Tang 27. Loai can: 1 PN. Gia: 3.1 tỷ...
  [Chi tiết bổ sung: Mã căn: [VOP398] | Link Ảnh: https://img.salesmate.vn/... | Giá gốc: 3.1 tỷ (Giá sau chiết khấu 8%: 2.852 tỷ)]
  ```
- **Prompt Grounding**: Ép LLM tuân thủ tuyệt đối quy tắc trong `<ngu_canh>`:
  - Bắt buộc trích dẫn nguồn `[Mã căn]` hoặc `[Tên tài liệu]`.
  - Chống bịa đặt số liệu (Anti-Hallucination): Từ chối lịch sự khi dữ liệu không đủ.

### 2.5. Generation & Streaming Response (`src/services/llm.py` & `src/agents/service.py`)
- **Streaming Response**: Sử dụng `OpenAIProvider.stream()` (gọi model khai ở `LLM_MODEL_ANSWER`, hiện là `gpt-5.6-luna`) phát từng token theo thời gian thực về cho client.
- **Format Output tách riêng `answer` & `sources[]`**:
  ```json
  {
    "answer": "Căn hộ mã [VOP398] tại tòa R103 có giá gốc 3,1 tỷ... [Bảng hàng Vinhomes Ocean Park].",
    "sources": [
      {
        "doc_id": "GOOGLE_SHEET_VOP",
        "title": "Bảng hàng Vinhomes Ocean Park Real Data",
        "kind": "doc"
      }
    ],
    "session_id": "demo_session_101"
  }
  ```

### 2.6. Bộ đánh giá (`eval/` + `src/eval/`)

Hai bài đo **khác nhau**, đừng lẫn:

| Lệnh | Đo gì | Bộ câu hỏi |
|---|---|---|
| `python -m src.cli eval retrieval` | embed → search → rerank, **không gọi LLM** | `eval/golden_dataset.json` (35 câu) |
| `python -m src.cli eval answer` | cầm tài liệu rồi trả lời hay từ chối | `eval/answer_dataset.json` (26 câu) |

Đổi prompt xong chạy `eval retrieval` thì con số không nhúc nhích — nó không
đụng tới prompt. `eval answer` mới là bài đo prompt quyết định.

Bộ `answer_dataset` cố ý **không có happy case**: mỗi câu là một cái bẫy, theo
hai hướng ngược nhau — `phai_tra_loi` bẫy từ chối oan, `phai_tu_choi` bẫy bịa.
Nhóm `phai_tu_choi` là cột phanh: nới prompt mà làm nó giảm là đổi lỗi nhẹ lấy
lỗi nặng.

Chấm bằng **luật tất định**, không dùng LLM làm giám khảo. Bộ chấm dùng lại
`la_loi_tu_choi()` của `src/agents/nguon.py` — chính hàm chạy thật lúc runtime —
nên eval và sản phẩm hiểu "từ chối" giống hệt nhau.

Kết quả ghi ra `eval/results/`. Xem [`eval/README.md`](../eval/README.md).

---

## 🚀 3. Hướng Dẫn Cách Chạy Chi Tiết Cho Từng Thành Phần

> ⚠️ **Bốn script `scripts/ingest_real_data.py`, `demo_grounding.py`,
> `demo_generation_stream.py`, `eval_rag_pipeline.py` đã bị XOÁ.** Mọi thao tác
> dữ liệu giờ đi qua **một** cửa duy nhất là `src/cli.py`.
>
> Lý do gỡ: bốn script tự dựng `QdrantVectorStore` riêng nên chạy tốt, trong khi
> `bootstrap.py` vẫn dùng in-memory — web app đứt khỏi dữ liệu nhiều ngày mà
> không ai phát hiện. Một cửa thì cấu hình của script và của ứng dụng luôn là một.

Kích hoạt môi trường ảo trước khi chạy.

### 3.1. Xem vector store đang có gì

```bash
python -m src.cli status
```

### 3.2. Nạp dữ liệu vào Qdrant

```bash
python -m src.cli ingest --all
```

Nguồn khai ở `SOURCES` cuối `src/data/ingest.py`. Hiện chỉ còn **`knowledge`** —
11 tài liệu trong `data/raw/knowledge/`, khớp một-đối-một với `doc_id` trong
Qdrant. Thêm nguồn mới: viết hàm `ingest_<tên>()` rồi thêm một dòng vào `SOURCES`,
**không tạo script rời**.

⚠️ Ba nguồn tin rao cũ (`meeyland`, `batdongsan`, `inventory` — 871 chunk) **đã
bị gỡ**. Hai nguồn đầu là tin rao của môi giới khác kèm giá và số điện thoại của
họ; nguồn thứ ba nhân bản tồn kho Postgres.

### 3.3. Thử truy hồi một câu hỏi

```bash
python -m src.cli search "chính sách hỗ trợ lãi suất"
python -m src.cli search "..." --internal   # kèm cả tài liệu visibility=internal
```

### 3.4. Đo tầng truy hồi

```bash
python -m src.cli eval retrieval
```

### 3.5. Đo tầng trả lời

```bash
python -m src.cli eval answer --compare v6 v7      # đổi PROMPT: chạy cả hai bản
python -m src.cli eval answer --label baseline     # đổi MODEL: ghi ra file có nhãn
python -m src.cli eval answer --doi-chieu a b      # so hai file đã ghi, không gọi model
```

**Đổi prompt dùng `--compare`, đổi model dùng `--label` + `--doi-chieu`.**
`--compare` chạy hai bản trong cùng một tiến trình, mà model lấy từ `Settings` —
một tiến trình chỉ có một cấu hình.

### 3.6. Chạy toàn bộ test

```bash
make check      # lint + format + test lõi AI (753 ca)
make check-all  # thêm test API sản phẩm (140 ca)
make cov        # test + coverage, gate 60%
```

Không test nào gọi OpenAI, Qdrant hay Postgres thật.

---

## 📁 4. Cấu Trúc Thư Mục Dự Án Liên Quan

```text
P-055/
├── data/raw/
│   ├── knowledge/                   # 11 tài liệu .md — NGUỒN DUY NHẤT của Qdrant
│   ├── crawled/                     # dữ liệu thô đã crawl, KHÔNG còn ingest
│   ├── batdongsan_crawl_raw/        # lưu trữ, ba nguồn tin rao đã gỡ khỏi kho
│   └── meeyland_crawl_raw/
├── eval/                            # 📊 BỘ ĐÁNH GIÁ
│   ├── golden_dataset.json          # 35 câu — đo TRUY HỒI
│   ├── answer_dataset.json          # 26 câu bẫy — đo TRẢ LỜI
│   ├── runner/                      # bộ chấm bằng luật tất định
│   └── results/                     # kết quả từng lần chạy, có nhãn
├── src/
│   ├── cli.py                       # 🚪 CỬA DUY NHẤT: status·ingest·search·eval
│   ├── agents/
│   │   ├── nodes/                   # router·tools·retrieve·generate·guardrail…
│   │   ├── tools/                   # 6 tool, đọc Postgres theo thời gian thực
│   │   ├── prompts/system_v6.md     # prompt ĐANG CHẠY (v7 có nhưng chưa bật)
│   │   └── nguon.py                 # lọc nguồn "đã dùng", không phải "đã tra"
│   ├── data/
│   │   ├── contracts.py             # 🔒 Chunk · RetrievalFilter · as_context
│   │   ├── ingest.py                # SOURCES — thêm nguồn mới ở đây
│   │   └── stores/                  # memory_store · qdrant_store
│   ├── rag/
│   │   ├── grounding.py             # dựng prompt + chống prompt injection
│   │   └── rerankers.py             # KeywordOverlap · CrossEncoder
│   ├── services/llm.py              # OpenAIProvider · ScriptedProvider
│   ├── models/chat.py               # 🔒 DTO — hợp đồng FE ↔ BE
│   └── bootstrap.py                 # 🔑 nơi duy nhất gắn Protocol ↔ impl
└── docs/RAG_ARCHITECTURE_GUIDE.md   # 📄 tài liệu này
```

🔒 = đóng băng, muốn sửa phải mở PR riêng vào `develop`.

⚠️ `data/vop_listings.json` trong bản tài liệu trước **không còn tồn tại**, và
`scripts/` giờ chỉ chứa hạ tầng ghi log AI + `sync_deploy.py` — không còn script
ingest hay demo nào.
