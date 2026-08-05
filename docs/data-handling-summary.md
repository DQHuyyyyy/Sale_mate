# Data Handling — Tổng hợp thay đổi (Viet, cập nhật 2026-08-05)

> Ghi lại toàn bộ thay đổi thuộc module **Data Handling** để leader review và
> team tiếp tục triển khai. Đối chiếu trực tiếp với `git log`/`git diff` lúc
> viết — không dựa vào trí nhớ, nên số liệu ở đây đảm bảo khớp code thật.

**Kết quả cuối:** 10/10 mục Data Handling xong (9 mục chính thức trong sprint
tracker + khảo sát nguồn). 99/99 test pass. Qdrant Cloud có **803 chunk** từ
**485 tài liệu**, **6/6 nhóm tài liệu kiến thức chung** đã có nội dung thật.
**Đúng kiến trúc "hai loại dữ liệu, hai đường đi":** dữ liệu có cấu trúc (100
căn tồn kho) nằm trong **Postgres/Supabase thật** (query SQL), văn bản dài
(chính sách, tiện ích, pháp lý) nằm trong **Qdrant** (vector search/RAG).

## 2026-08-05 — Nâng tồn kho từ CSV lên Postgres thật

Trước đó `InventoryLookupTool` đọc trực tiếp CSV mỗi lần gọi (bản vá tạm) —
giờ chuyển hẳn sang query SQL trên bảng `inventory_units` trong Supabase
Postgres, đúng kiến trúc "có cấu trúc → Postgres" mà leader yêu cầu.

| File | Tác dụng |
|---|---|
| `src/data/stores/inventory_db.py` (mới) | `InventoryDB` — SQLAlchemy Core, upsert bằng DELETE+INSERT (portable giữa SQLite test và Postgres thật, không dùng cú pháp riêng của Postgres) |
| `scripts/migrate_inventory_to_postgres.py` (mới) | Nạp 100 căn từ CSV vào Postgres — idempotent, chạy lại an toàn |
| `src/agents/tools/inventory.py` (sửa) | Query Postgres qua `asyncio.to_thread` thay vì đọc CSV |
| `src/data/sources/inventory.py` (không đổi) | Vẫn là nguồn CSV gốc — chỉ dùng để migrate, không còn được tool gọi trực tiếp |

**Verify thật:** migration nạp đúng 100/100 căn; tool tra `VOP834` trả đúng dữ
liệu thật từ Postgres (`source: inventory:postgres`, giá 3,4 tỷ, "Còn trống").
16 test mới/sửa, không test nào gọi Postgres thật (SQLite in-memory +
`StaticPool` để tương thích với `asyncio.to_thread`).

**Supabase Storage** (ảnh) vẫn CHƯA dùng — cơ hội còn để ngỏ nếu cần ảnh có
URL public cho tồn kho.

---

## 0. Toàn bộ đóng góp trên nhánh `viet` (so với `main`)

So `git log main..viet`, lọc đúng commit do **Bùi Hoàng Việt** tạo (loại các
merge commit mang theo code của Huy — `d4c7fea`, `b8beac1`, `1c44f30`,
`b39b6a3` — không phải phần Việt viết, chỉ là kéo `develop` về qua lệnh merge).

| Ngày | Commit | Nội dung |
|---|---|---|
| 2026-07-29 | (thiết lập ban đầu) | Tạo repo local, nhánh `viet`, cấu hình hook ghi AI log |
| — | `61ca7af` | Sửa hook ghi AI log chạy được trên Windows |
| 2026-08-01 | `e1e4810` | **Bắt đầu Data Handling:** xử lý tồn kho (`src/data/sources/inventory.py`), crawl thủ công + parser batdongsan.com.vn (`src/data/crawling/batdongsan.py`), dựng pipeline ingest đầu tiên + demo agent — 805 dòng, 11 file |
| 2026-08-02 | `aad7484` | Chuyển từ vector store tạm sang **Qdrant thật** (Docker local lúc đó), ingest 158 chunk thật |
| 2026-08-03 → 2026-08-04 | *(hôm nay, xem chi tiết bên dưới)* | Hoàn thành toàn bộ 9 mục Data Handling còn lại: thêm nguồn meeyland.com + tài liệu kiến thức chung, sửa bug chunking, sửa phân quyền, chuyển Qdrant Cloud, sửa tool tồn kho, golden eval set — **14 file sửa + 13 file mới, +379/-73 dòng** (đang chờ commit) |

**Tổng cộng cả nhánh so với `main`:** 134 file, +17.486/-566 dòng — nhưng phần
LỚN trong số đó (`src/models/`, `src/services/portal.py`,
`tests/test_api/*`...) là code của Huy/team đã có sẵn trên `develop`, được
kéo vào nhánh `viet` qua lệnh `git merge develop` (commit `c511311`) để cập
nhật base — **không phải phần Việt viết**. Phần thật sự do Việt đóng góp cho
Data Handling nằm trong 3 commit + phần đang chờ commit ở bảng trên.

---

## 1. Hạ tầng đổi — Qdrant Cloud + Supabase

Trước đây chạy Qdrant qua Docker local (`make infra`). Từ hôm nay chuyển sang
**Qdrant Cloud** (cluster thật) + cấu hình sẵn **Supabase** (Postgres + Storage,
chưa dùng tới, xem mục 8).

**File đổi:** `.env` (không commit — đã gitignore, mỗi máy tự set theo mẫu dưới).

```bash
QDRANT_URL=https://20440bb8-...aws.cloud.qdrant.io
QDRANT_API_KEY=<key thật, hỏi Viet>
QDRANT_COLLECTION=documents_chunks
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_BUCKET=apartment-images
DATABASE_URL=postgresql://postgres...supabase.com:5432/postgres
```

**Hệ quả code:** `QdrantVectorStore` cần tham số `api_key` để xác thực với
Cloud (Docker local không cần). Đã sửa 5 script ingest để truyền đúng
`settings.qdrant_api_key` — xem mục 3.2.

---

## 2. File MỚI tạo

### 2.1. Nguồn dữ liệu (`src/data/`)

| File | Tác dụng |
|---|---|
| `src/data/crawling/meeyland.py` | Crawler tự động cho meeyland.com (tin đăng Vinhomes Ocean Park) — crawl trực tiếp qua HTTP, không cần thu thập thủ công như batdongsan. Có loại bỏ số điện thoại môi giới (regex `_PHONE_RE`, áp cho cả `title` và mô tả). |
| `src/data/sources/knowledge_docs.py` | Loader cho tài liệu kiến thức chung dạng Markdown (chính sách, pháp lý, tiện ích...). Đọc file `.md` có front-matter bắt buộc `title`/`section`/`visibility` — báo lỗi ngay nếu thiếu, tránh gắn nhầm quyền cho nội dung nhạy cảm. |
| `src/data/metadata_schema.py` | Định nghĩa **6 khoá metadata bắt buộc** cho MỌI nguồn: `visibility`, `section`, `project`, `source_site`, `image_urls`, `version`. Có hàm `validate_metadata()` để chặn sớm nguồn mới thiếu khoá. Đây là "hợp đồng ngầm" giữa các nguồn dữ liệu — không có trong `contracts.py` (đóng băng) vì chỉ là quy ước nội bộ module data. |

### 2.2. Script ingest (`scripts/`)

| File | Tác dụng |
|---|---|
| `scripts/ingest_more_sources.py` | Crawl + ingest toàn bộ tin meeyland.com vào Qdrant. Sau khi ingest, tự động so tin hiện có với tin đang active trong Qdrant — tin nào bị gỡ khỏi site thì đánh dấu `is_active=False` (không xoá, giữ làm lịch sử). |
| `scripts/ingest_knowledge_docs.py` | Đọc toàn bộ `.md` trong `data/raw/knowledge/`, validate schema, ingest vào Qdrant qua `IngestPipeline` có sẵn (không cần sửa chunker/embedder/store). |
| `scripts/eval_retrieval.py` | Chạy `Retriever` thật (embed → search Qdrant → rerank) trên bộ câu hỏi vàng (`eval/golden_dataset.json`), đo hit@5 + coverage, ghi kết quả ra `eval/results/retrieval_eval.json`. Dùng filter `[public, internal]` để đo đúng năng lực retrieval, tách biệt khỏi bài toán phân quyền. |

### 2.3. Dữ liệu eval (`eval/`)

| File | Tác dụng |
|---|---|
| `eval/golden_dataset.json` | 12 câu hỏi kiểm thử, mỗi câu gắn `expected_doc_id` lấy từ dữ liệu THẬT đã ingest (không bịa) — dùng để đo retrieval có tìm đúng tài liệu không. |
| `eval/results/retrieval_eval.json` | Kết quả chạy `eval_retrieval.py` gần nhất (tự động ghi đè mỗi lần chạy) — chi tiết từng câu, coverage, đúng/sai. |

### 2.4. Test (`tests/`)

| File | Test gì |
|---|---|
| `tests/test_data/test_crawling_meeyland.py` | Parser meeyland.com — trích đúng trường, loại SĐT (title + mô tả), dedupe link. |
| `tests/test_data/test_metadata_schema.py` | `validate_metadata()` báo lỗi đúng khi thiếu khoá; cả 3 nguồn (inventory/batdongsan/meeyland) đều đạt schema; `Chunk.version` lấy đúng ngày ingest. |
| `tests/test_data/test_knowledge_docs.py` | Loader `.md` — parse đúng front-matter, báo lỗi rõ khi thiếu/sai `visibility`. |
| `tests/test_data/test_qdrant_store_lifecycle.py` | 2 method mới `list_active_doc_ids()`/`mark_inactive()` — dùng client Qdrant giả (không gọi Qdrant thật, đúng quy ước dự án). |

---

## 3. File ĐÃ SỬA — chi tiết từng chỗ đổi

### 3.1. `src/data/ingestion/chunkers.py` — sửa **bug thật**

**Trước:** `ParagraphChunker` chỉ cắt cứng (`_hard_split`) đoạn văn quá dài khi
nó là đoạn ĐẦU TIÊN (buffer rỗng). Đoạn dài đứng SAU một đoạn ngắn (rất phổ
biến: tiêu đề ngắn rồi "Mô tả:" dài) bị ghép nguyên vào buffer, không cắt.

**Hậu quả đo được:** quét dữ liệu thật phát hiện 186/468 tài liệu có chunk vượt
target 900 ký tự, dài nhất tới **3293 ký tự** (gấp 3.6 lần).

**Đã sửa (dòng `split()`):** sau khi flush buffer, kiểm tra `tail + đoạn mới`
có vượt target không — nếu vượt thì gọi `_hard_split()` ngay, thay vì gán
thẳng làm buffer mới. Verify lại: 0/803 chunk vượt 900 trên Qdrant thật.

### 3.2. Scripts ingest — thêm `api_key` cho Qdrant Cloud

`scripts/chat_demo_rag.py`, `scripts/ingest_batdongsan.py`,
`scripts/ingest_inventory.py` (+ 2 file mới ở mục 2.2): tất cả đổi

```python
QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection)
```

thành

```python
QdrantVectorStore(settings.qdrant_url, settings.qdrant_collection, api_key=settings.qdrant_api_key)
```

Thiếu tham số này chạy được với Docker local (không cần auth) nhưng **vỡ hoàn
toàn** với Qdrant Cloud (401/403).

### 3.3. `src/data/stores/qdrant_store.py` — thêm 2 method + fix index

- **`list_active_doc_ids(source_site)`** và **`mark_inactive(doc_ids)`** — 2
  method MỞ RỘNG ngoài `VectorStore` Protocol (không đụng `contracts.py` đóng
  băng), chỉ dùng nội bộ trong script ingest. Dùng để phát hiện tin đã bị gỡ
  khỏi nguồn và đánh dấu hết hiệu lực (mục "Quản lý phiên bản tài liệu").
- **Thêm index `metadata.source_site`** vào `ensure_collection()`: Qdrant
  Cloud từ chối filter trên field chưa có index (lỗi 400 Bad Request) —
  Docker local không bắt buộc nên lỗi này ẩn từ trước, chỉ lộ khi đổi hạ tầng.

### 3.4. `src/data/crawling/batdongsan.py` — thêm 2 khoá metadata

Thêm `"project": "Vinhomes Ocean Park Gia Lâm"` và `"version": <ngày crawl>`
vào `metadata` — trước đó thiếu 2 khoá này (phát hiện khi làm mục "metadata
schema" và "quản lý phiên bản").

### 3.5. `src/data/sources/inventory.py` — 2 thay đổi quan trọng

1. **Đổi `visibility` từ `"public"` thành `"internal"`.** Đây là tồn kho THẬT
   của team — sau khi đọc sprint tracker phát hiện Đạt đang build màn hình
   Admin/Sale riêng biệt (khác giả định "sản phẩm hoàn toàn public" ban đầu),
   xác nhận lại với user: tồn kho chỉ Admin/Sale thấy qua RAG, portal công
   khai KHÔNG được lộ ra.
2. Thêm `source_site: "noi-bo"`, `image_urls: []` (ảnh có trên máy nhưng chưa
   có server public để trỏ URL — để rỗng, không bịa), `local_photo_files`,
   `version`.

**Cảnh báo cho ai đọc code cũ:** nếu thấy tài liệu/test nào giả định tồn kho
là `public`, đó là SAI theo quyết định mới nhất — đã có test
(`test_inventory_source.py`) chặn regression.

### 3.6. `src/agents/tools/inventory.py` — sửa từ mock hư cấu sang dữ liệu thật

**Phát hiện:** `InventoryLookupTool` (tool để agent tra tồn kho) dùng dữ liệu
**hoàn toàn hư cấu** — "Lakeside Metropole", "The Origin Riverside" — không
liên quan gì tới Vinhomes Ocean Park, tách biệt hoàn toàn khỏi 100 căn thật.

**Đã sửa:** đọc thẳng `load_inventory_csv()` (từ `src/data/sources/inventory.py`)
ở MỖI lần gọi — gần nhất với "thời gian thực" khi chưa có DB/ERP thật. Đổi
tham số `InventoryArgs`: bỏ `project` (dữ liệu thật chỉ có 1 dự án), dùng
`unit_code`/`building`/`unit_type`.

*Lưu ý ranh giới module:* file này nằm trong `src/agents/`, nhưng
`agents/contracts.py` dòng 6 ghi rõ "Chủ sở hữu: viet" — sửa đúng thẩm quyền,
không phải lấn phạm vi. Task "Xử lý tồn kho theo thời gian thực" cũng thuộc
Data Handling theo sprint tracker.

**Còn thiếu, không tự làm được:** chưa nối API doanh nghiệp thật vì chưa có hệ
thống ERP để nối.

### 3.7. `eval/results/report.md` — thêm mục 1a Retrieval Evaluation

Thêm bảng kết quả eval thật (hit@5, coverage) + 1 phát hiện quan trọng: câu
hỏi hoàn toàn không có dữ liệu vẫn cho coverage 0.77 (vượt xa ngưỡng guardrail
0.35 của module agents) — coverage một mình không đủ tin cậy làm rào chắn.

### 3.8. `README.md` — thêm hướng dẫn nạp dữ liệu

Thêm mục "4. Nạp dữ liệu RAG thật vào Qdrant" — liệt kê đủ 4 script ingest,
giải thích script nào cần xin file từ Viet (`data/raw/` bị gitignore) và
script nào chạy được ngay (crawl trực tiếp).

---

## 4. Bug phát hiện — ĐÃ báo, KHÔNG tự sửa (ngoài phạm vi module data)

### 4.1. `src/agents/nodes/router.py` — 2 bug, thuộc module AI Agent (Huy)

1. Từ khoá "căn hộ"/"tìm nhà" → intent `LISTING`, nhưng `needs_retrieval` chỉ
   bật cho `{document, legal, price}` (dòng 55) — **toàn bộ tìm kiếm tin đăng
   qua chat hiện không chạy** dù dữ liệu đầy đủ (379 tin đăng thật trong
   Qdrant).
2. Câu hỏi tiện ích đôi khi bị LLM router phân sai thành `LISTING` thay vì
   `DOCUMENT`, dù chính prompt của router liệt kê "tiện ích" thuộc `document`.

**Cách tái hiện:** chạy `scripts/chat_demo_rag.py`, hỏi "Cho tôi thông tin căn
hộ 3 phòng ngủ" → trả lời "chưa đủ dữ liệu" dù Qdrant có hàng trăm tin phù hợp.

### 4.2. `src/services/portal.py` — data hư cấu tương tự, khác phạm vi

`InMemoryPortalRepository` cũng dùng "Lakeside Metropole" giả cho trang portal
tìm kiếm công khai (`Home: tìm kiếm căn hộ` — việc của Đạt). Không sửa vì đây
là feed cho portal, không phải "tồn kho" theo đúng nghĩa task được giao.

---

## 5. Dữ liệu KHÔNG nằm trong git — cần chia sẻ riêng

`data/` bị `.gitignore` toàn bộ (tránh commit data lớn) — các file sau chỉ có
trên máy Viet, teammate cần xin qua Drive/kênh riêng nếu muốn chạy ingest:

- `data/raw/inventory.csv` + `data/raw/photos/` — tồn kho 100 căn.
- `data/raw/*.html` (33 file) — tin batdongsan.com.vn lưu tay.
- `data/raw/knowledge/internal/*.md` (4 file: chính sách bán hàng, tiến độ
  thanh toán, bảng giá dịch vụ, tiến độ xây dựng) — số liệu tra cứu công khai
  từ Vinhomes/broker, có trích nguồn, **có ghi rõ trong từng file** là cần xác
  nhận lại với CĐT trước khi cam kết với khách (chiết khấu/tiến độ đổi theo
  đợt).
- `data/raw/knowledge/public/*.md` (2 file: tiện ích, pháp lý & thủ tục) — có
  trích nguồn thật (thuvienphapluat.vn, market.vinhomes.vn...).

---

## 6. Cách chạy lại từ đầu (cho teammate)

```bash
# 1. Cài đặt (nếu chưa)
python3.11 -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Điền .env — xin Viet giá trị QDRANT_URL/QDRANT_API_KEY/SUPABASE_* thật
cp .env.example .env

# 3. Xin data/raw/ (inventory.csv, photos/, *.html, knowledge/) từ Viet qua Drive

# 4. Ingest lần lượt (thứ tự không bắt buộc, trừ ingest_more_sources hơi lâu ~15 phút)
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_inventory.py
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_batdongsan.py
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_more_sources.py
PYTHONUTF8=1 PYTHONPATH=. python scripts/ingest_knowledge_docs.py

# 5. Verify
PYTHONUTF8=1 PYTHONPATH=. python -m pytest tests/ -q
PYTHONUTF8=1 PYTHONPATH=. python scripts/eval_retrieval.py
PYTHONUTF8=1 PYTHONPATH=. python scripts/chat_demo_rag.py   # cần OPENAI_API_KEY
```

---

## 7. Trạng thái cuối cùng (verify thật, 2026-08-04)

| Chỉ số | Giá trị |
|---|---|
| Tổng chunk trong Qdrant Cloud | 803 |
| Tổng tài liệu (unique doc_id) | 485 |
| Nguồn: tồn kho nội bộ (internal) | 100 |
| Nguồn: tài liệu kiến thức chung | 6 (2 public + 4 internal) |
| Nguồn: batdongsan.com.vn (public) | 33 |
| Nguồn: meeyland.com (public) | 346 |
| Chunk vượt target 900 ký tự | 0 |
| Chunk thiếu metadata bắt buộc | 0 |
| Chunk còn lộ số điện thoại | 0 |
| Lỗi phân loại visibility sai | 0/485 |
| Hit@5 (golden eval, 11 câu có dữ liệu) | 9/11 = 82% |
| Test suite | 92/92 pass |
| Lint (`ruff check`/`format`, phạm vi `src/ tests/`) | Sạch |

---

## 8. Việc còn lại — cần team quyết định, không tự làm

- **Nối ERP thật cho tồn kho real-time** — chưa có hệ thống ERP để nối.
- **Sửa 2 bug router** (`src/agents/nodes/router.py`) — báo Huy, mục 4.1.
- **Guardrail chỉ dựa coverage chưa đủ tin cậy** — báo agents, xem
  `eval/results/report.md` mục 1a.
- **Hạ tầng ảnh public cho tồn kho** — Supabase Storage bucket
  `apartment-images` đã cấu hình sẵn trong `.env` nhưng chưa có code dùng —
  cơ hội giải quyết gap "tồn kho có ảnh nhưng chưa có URL public".
- **`services/portal.py` dùng data hư cấu** — báo Đạt/Phúc, mục 4.2.
- **Lịch sử nhiều phiên bản của tài liệu CÒN hiệu lực nhưng đổi nội dung** —
  cần đổi cách đặt chunk id, ảnh hưởng retrieval, phải bàn với team trước.
- **Cảnh báo mâu thuẫn giữa batdongsan và meeyland** — không có mã căn chung
  giữa 2 site bên thứ ba để khớp an toàn, chưa làm để tránh tạo "mâu thuẫn giả".
