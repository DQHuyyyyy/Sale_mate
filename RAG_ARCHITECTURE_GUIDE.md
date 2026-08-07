# Hướng Dẫn Kiến Trúc & Cách Chạy RAG Pipeline (SalesMate AI Core)

Tài liệu này tổng hợp toàn bộ hệ thống **RAG Pipeline (Retrieval-Augmented Generation)**, mối liên kết giữa dữ liệu thật tại thư mục `data/` với mã nguồn `src/data/`, và hướng dẫn chi tiết cách chạy từng thành phần.

---

## 📐 1. Mối Liên Kết Giữa Thư Mục `data/` và `src/data/`

Dự án phân tách rõ ràng giữa **Dữ liệu thật** và **Logic lập trình**:

```
                                  ┌────────────────────────────────────────┐
                                  │       FILE DỮ LIỆU THẬT: data/         │
                                  │ - data/vop_listings.json (Real Sheet)  │
                                  │ - data/raw/ (CSV Tồn kho & Excel)      │
                                  └───────────────────┬────────────────────┘
                                                      │
                                                      │ (Script nạp đọc file)
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

- **Thư mục `data/` (Ngoài root)**: Nơi lưu trữ **Dữ liệu thật** (file `vop_listings.json` chứa 100+ căn Vinhomes Ocean Park + ảnh + giá + chiết khấu, các file CSV tồn kho nội bộ).
- **Thư mục `src/data/` (Trong src)**: Nơi chứa **Mã nguồn thuật toán** (Code parser đọc file, code chunking, code tạo vector, code Qdrant store, code Cross-Encoder rerank).

---

## 🧩 2. Tổng Quan Các Thành Phần Đã Build Trong RAG

### 2.1. Ingestion & Data Handling (`src/data/ingestion/` & `src/data/parsers.py`)
- **Dữ liệu thô**: Parse từ `data/vop_listings.json` (Real Data từ Google Sheet).
- **Metadata Schema**: Đóng gói đầy đủ các trường: `ma_can`, `price`, `area`, `num_bedrooms`, `building`, `doc_kind` (`"listing"` vs `"policy"`), `image_url` (Link Ảnh căn hộ), `visibility` (`"public"` vs `"internal"`).
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
- **Streaming Response**: Sử dụng `OpenAIProvider.stream()` (gọi `gpt-4o-mini`) phát từng token theo thời gian thực về cho client.
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

### 2.6. RAG Evaluation Suite (`eval/` & `scripts/eval_rag_pipeline.py`)
- **Golden Dataset**: Bộ 18 test cases chuẩn phân làm 4 nhóm (Tra cứu đơn, Có ràng buộc số, So sánh nhiều căn, Câu hỏi bẫy).
- **Chỉ số Đạt Được**:
  - 🎯 **Hit Rate@3**: **100.0%**
  - 🎯 **Hit Rate@5**: **100.0%**
  - 🛡️ **Refusal Accuracy**: **100.0%**
  - ⚡ **Mean Latency**: **3.74 ms** (P90 = 6.24 ms)

---

## 🚀 3. Hướng Dẫn Cách Chạy Chi Tiết Cho Từng Thành Phần

Đảm bảo bạn đã kích hoạt môi trường ảo Python trước khi chạy các lệnh dưới đây.

### 3.1. Chạy Ingest Dữ Liệu Thật từ `data/vop_listings.json`
Lệnh này sẽ nạp 100+ căn bất động sản real data kèm link ảnh và chính sách bán hàng vào hệ thống:

```powershell
python scripts/ingest_real_data.py
```

---

### 3.2. Chạy Demo Nguồn & Prompt Grounding
Kiểm tra khả năng ép LLM trích dẫn `[Mã căn]` và từ chối khi không có dữ liệu:

```powershell
python scripts/demo_grounding.py
```

---

### 3.3. Chạy Demo Generation & Streaming (Tách riêng `answer` và `sources[]`)
Kiểm tra luồng sinh chữ real-time từ OpenAI / Mock Provider và xem cấu trúc JSON đầu ra cho Frontend:

```powershell
python scripts/demo_generation_stream.py
```

---

### 3.4. Chạy Benchmark Đánh Giá RAG Pipeline (Hit Rate & Latency)
Chạy bộ kiểm thử 18 câu test trên toàn bộ Pipeline RAG và xuất báo cáo tại [eval/results/eval_report.md](file:///d:/P-055/eval/results/eval_report.md):

```powershell
python scripts/eval_rag_pipeline.py
```

---

### 3.5. Chạy Toàn Bộ 162 Unit & Integration Tests
Chạy kiểm thử tự động toàn bộ codebase (kiểm tra lint, format, RAG nodes, stores, tools):

```powershell
python -m pytest
```

---

## 📁 4. Cấu Trúc Thư Mục Dự Án Liên Quan

```text
P-055/
├── data/                            # 📁 CHỨA FILE DỮ LIỆU THẬT
│   ├── vop_listings.json            # 100+ căn Vinhomes Ocean Park real data
│   └── raw/                         # File CSV tồn kho & Excel thô
├── eval/                            # 📊 BỘ ĐÁNH GIÁ EVALUATION
│   ├── golden_dataset.json          # 18 test cases kiểm thử chuẩn
│   └── results/                     # Báo cáo kết quả eval (eval_report.md)
├── scripts/                         # 📜 SCRIPT CHẠY DEMO & INGEST
│   ├── ingest_real_data.py          # Script nạp dữ liệu thật từ data/
│   ├── demo_generation_stream.py    # Script demo streaming & JSON output
│   ├── demo_grounding.py            # Script demo prompt & anti-hallucination
│   └── eval_rag_pipeline.py         # Script chạy benchmark Hit Rate & Latency
├── src/                             # 🧠 MÃ NGUỒN CHÍNH DỰ ÁN
│   ├── agents/                      # LangGraph Agent & Prompt nodes
│   │   ├── nodes/generate.py        # Prompt Grounding template
│   │   └── prompts/system_v1.md     # System prompt quy định citation
│   ├── data/                        # Core Data Handling & Retrieval
│   │   ├── contracts.py             # Schema Chunk, RetrievalFilter, as_context
│   │   ├── parsers.py               # Parse dữ liệu thô
│   │   ├── retrieval/               # Reranker & DefaultRetriever
│   │   └── stores/                  # MemoryStore & QdrantStore
│   ├── services/llm.py              # OpenAIProvider & ScriptedProvider
│   └── models/chat.py               # ChatResponse DTO (.answer & .sources)
└── RAG_ARCHITECTURE_GUIDE.md        # 📄 Tài liệu hướng dẫn này
```
