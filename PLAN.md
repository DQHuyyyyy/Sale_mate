# Kế hoạch triển khai — SalesMate (P-055)

> Bảng điều khiển của lead. Cập nhật cột **Trạng thái** mỗi cuối tuần.
> Lập ngày 01/08/2026 · Hết tuần 1.

## Mốc thời gian

| Tuần | Từ → Đến | Mục tiêu ra được cái gì |
|---|---|---|
| 1 | 27/07 → 01/08 | ✅ Codebase 3 module · portal FE · CI xanh |
| 2 | 02/08 → 08/08 | **Live URL chạy** · Qdrant thật · auth · trang chi tiết tin |
| 3 | 09/08 → 15/08 | **RAG bật** — trả lời có trích nguồn thật |
| 4 | 16/08 → 22/08 | Admin console · golden set · LangSmith |
| 5 | 23/08 → 29/08 | **RAGAS eval** · video demo · polish |
| 6 | 30/08 → 05/09 | Pitch deck · gom đủ 10 deliverable · tổng duyệt |

⚠️ **Ngày Demo Day là giả định 05/09.** Lead xác nhận với BTC rồi sửa lại bảng này.

---

## 3 việc chặn — lead xử lý trước, không giao được cho ai

| # | Việc | Vì sao chặn | Hạn |
|---|---|---|---|
| 1 | **Nạp credit OpenAI** (hoặc chốt provider free) | Không có LLM thì widget không trả lời được, mà widget là sản phẩm | 02/08 |
| 2 | **Viết lại `Core.md`** | `Giaodien.md` đã ghi "lõi AI đang thiết kế lại". `viet` không biết xây agent gì | 04/08 |
| 3 | **Chốt nguồn tài liệu cho RAG** | Không có tài liệu thì không có gì để truy hồi, cả module Data đứng | 04/08 |

**Về việc 3** — sản phẩm đã đổi từ app nội bộ sang portal công khai, nên "tài liệu" cũng khác. Đề xuất: 15–20 tài liệu công khai về **thủ tục và pháp lý bất động sản Việt Nam** (sang tên sổ đỏ, thuế phí, hợp đồng đặt cọc, quy trình vay mua nhà, quy hoạch). Lấy từ cổng thông tin nhà nước, lưu PDF vào `data/documents/`. Vừa hợp với 4 quick-action của widget, vừa là thứ người dùng thật sự hỏi.

---

## Phân module và người sở hữu

| Module | Người | Thư mục | Nguyên tắc |
|---|---|---|---|
| Data handling | **dat** | `src/data/**` | Chỉ export qua `contracts.py` |
| AI core | **viet** | `src/agents/**` | Không import class cụ thể của Data |
| Interface (BE) | **phuc** | `src/api/**` · `src/services/**` | Router không chứa business logic |
| Interface (FE) | **huy** | `frontend/**` · `src/core/**` | Token màu ở `globals.css`, không hardcode |

`src/models/` và mọi `contracts.py` **đóng băng** — sửa phải mở PR riêng vào `develop`.

---

# TUẦN 2 · 02/08 → 08/08

**Mục tiêu tuần:** có Live URL truy cập được từ internet + hạ tầng thật thay cho đồ giả lập.

### 🟦 dat — Data

| Task | Định nghĩa xong |
|---|---|
| Bật Qdrant, đổi `bootstrap.py` sang `QdrantVectorStore` | Test hiện có pass với Qdrant thật |
| Script CLI `python -m src.data.ingest <file>` | Nạp được 1 PDF, `count()` > 0 |
| Loader cho PDF (`pdfplumber`) và Excel | `DocumentLoader.can_handle()` nhận đúng đuôi file |
| Nạp 15–20 tài liệu nguồn | Qdrant có ≥ 200 chunk |

### 🟩 viet — AI core

| Task | Định nghĩa xong |
|---|---|
| Kiểm thử router trên 20 câu hỏi thật | ≥ 80% phân đúng intent, có test |
| Prompt `system_v2.md` theo `Core.md` mới | Prompt có version, eval trước/sau |
| Tool `price_lookup` (mock) | Có test, không raise, trả `ToolResult` |
| Bật LangSmith tracing | Thấy trace từng node trên dashboard |

### 🟨 phuc — Interface BE

| Task | Định nghĩa xong |
|---|---|
| Postgres + SQLAlchemy + alembic migration đầu | `alembic upgrade head` chạy sạch |
| Bảng `users` · JWT · `POST /auth/login` | Test login đúng/sai |
| `SqlPortalRepository` thay `InMemory` | Đổi 1 dòng ở `bootstrap.py`, test cũ vẫn pass |
| Seed dữ liệu portal vào DB | `GET /listings` trả từ DB |

### 🟪 huy — FE + lead

| Task | Định nghĩa xong |
|---|---|
| **Deploy BE lên Render, FE lên Vercel** | URL trả 200 từ máy khác + incognito |
| UptimeRobot ping `/health` mỗi 5 phút | Render không ngủ |
| Trang chi tiết tin `/tin/[id]` | Responsive đủ 3 breakpoint |
| Trang danh sách `/mua-ban` có filter | Gọi API thật |
| Điền `JOURNAL.md` tuần 1–2 | ≥ 2 entry |

> 🔑 **Deploy là việc quan trọng nhất tuần 2.** Guidebook BTC nói rõ: deploy sớm để còn thời gian sửa lỗi triển khai. 0/12 đội cohort trước có CI/CD — ta đã có, đừng để mất lợi thế vì thiếu Live URL.

---

# TUẦN 3 · 09/08 → 15/08

**Mục tiêu tuần:** widget trả lời bằng dữ liệu thật, có chip nguồn. Đây là tuần chứng minh sản phẩm.

### 🟦 dat
- Chunking tôn trọng cấu trúc bảng (không cắt vỡ bảng giá)
- Metadata đầy đủ: `visibility` · `version` · `page` · `section`
- Versioning: nạp lại cùng `doc_id` → bản cũ `is_active=false`
- Rerank thật bằng **Cohere Rerank v3** (free 10 RPM) thay `PassthroughReranker`

### 🟩 viet
- **Bật `ENABLE_RAG = True`** trong `bootstrap.py`
- Node `retrieve` chạy thật, `generate` ép grounding theo context
- Phát event `route` + `sources` qua SSE
- Guardrail: chỉnh `COVERAGE_THRESHOLD` bằng số đo, không đoán

### 🟨 phuc
- `POST /documents` upload + `GET /documents/{id}/status` (tiến trình ingest)
- Phân quyền: `visibility` lọc theo role của token
- **Test rò rỉ**: user thường hỏi câu chỉ có trong tài liệu nội bộ → phải không thấy

### 🟪 huy
- Widget hiển thị **chip nguồn** từ event `sources`
- Hiển thị **route line** từ event `route`
- Trạng thái "chưa đủ dữ liệu" có viền cảnh báo
- Chụp màn hình mọi thứ cho README

> 🔑 **Cuối tuần 3 phải demo được:** hỏi "Thủ tục sang tên sổ đỏ gồm những gì?" → trả lời đúng + chip nguồn ghi tên tài liệu và phiên bản.

---

# TUẦN 4 · 16/08 → 22/08

**Mục tiêu tuần:** admin console + bắt đầu đo chất lượng.

### 🟦 dat
- Cảnh báo tài liệu mâu thuẫn (hai bản active nói khác nhau)
- Đo **retrieval recall** trên golden set, ghi số vào `eval/results/`

### 🟩 viet
- **Golden set 30–50 câu** trong `eval/` — gồm cả ca *phải từ chối* và ca *phân quyền*
- Harness chạy eval: `python -m src.eval.run`
- So sánh prompt v1 vs v2 bằng số

### 🟨 phuc
- API admin: danh sách tài liệu, re-index, xoá
- Rate limit · phân trang · endpoint search
- Log hành động nhạy cảm vào DB

### 🟪 huy
- Trang **Login** + trang **Admin console** (upload kéo-thả, bảng tài liệu, badge trạng thái ingest)
- Dark mode (BTC chấm UI/UX có nhắc)
- `WORKLOG.md` cập nhật đều

---

# TUẦN 5 · 23/08 → 29/08

**Mục tiêu tuần:** bằng chứng chất lượng + video. Hai thứ gần như không đội nào có.

### Cả team
| Việc | Người | Ghi chú |
|---|---|---|
| **RAGAS eval** — faithfulness · answer relevance · context precision/recall | viet | Ngưỡng > 0.7 |
| Báo cáo `eval/results/report.md` | viet + dat | Bảng số + ảnh chụp pytest |
| Đo độ trễ p95 và chi phí/câu | phuc | Đưa vào báo cáo |
| **Video demo 3–5 phút** | huy | Upload YouTube unlisted |
| Thử nghiệm với 5–10 người thật, thu phản hồi | cả team | Đưa vào báo cáo |
| Rà accessibility + responsive | huy | `:focus-visible` · `aria-live` · `prefers-reduced-motion` |

> 🔑 **Evaluation Evidence và Video Demo là hai deliverable dễ ghi điểm nhất** — cohort trước 10/12 đội thiếu eval, 12/12 đội thiếu video. Làm đủ hai cái này là vượt cả cohort.

---

# TUẦN 6 · 30/08 → 05/09

**Mục tiêu tuần:** đóng gói, không code tính năng mới.

| Việc | Người | Hạn |
|---|---|---|
| Pitch deck 10 slide (PDF, không PPTX) | huy | 02/09 |
| Thực hành thuyết trình 3 lần, canh 10 phút | cả team | 04/09 |
| Rà code: xoá `except` trần, thêm type hint, `make check` xanh | cả team | 01/09 |
| Kiểm tra Live URL trên máy khác + incognito | phuc | 03/09 |
| Gom đủ 10 deliverable, đối chiếu checklist | huy | 03/09 |
| Chuẩn bị Q&A: "chống ảo giác thế nào?" · "scale ra sao?" · "chi phí/câu?" | cả team | 04/09 |

---

# Bảng 10 deliverable

| # | Deliverable | Vị trí | Người | Hạn | Trạng thái |
|---|---|---|---|---|---|
| 1 | Source code | `src/` · `frontend/` | cả team | 05/09 | 🟢 Đang chạy |
| 2 | README.md | `/README.md` | huy | 05/09 | 🟢 Xong, cập nhật dần |
| 3 | Architecture diagram | `docs/architecture_diagram.md` | huy | 05/09 | 🟢 Xong |
| 4 | AI Logs (LangSmith) | link + ảnh chụp | viet | 08/08 | 🔴 Chưa |
| 5 | **Live URL** | Render + Vercel | huy | **08/08** | 🔴 Chưa |
| 6 | **Video demo** | YouTube unlisted | huy | 29/08 | 🔴 Chưa |
| 7 | Pitch deck | `presentation/` PDF | huy | 02/09 | 🔴 Chưa |
| 8 | Journal | `JOURNAL.md` | huy | hàng tuần | 🔴 Chưa |
| 9 | Worklog | `WORKLOG.md` | cả team | hàng ngày | 🔴 Chưa |
| 10 | **Evaluation Evidence** | `eval/results/report.md` | viet + dat | 29/08 | 🔴 Chưa |

Ba cái in đậm là nơi cohort trước mất điểm nhiều nhất — ưu tiên cao nhất.

---

# Đường găng

```
Nạp credit LLM ──┐
                 ├──> viet bật RAG (T3) ──> golden set (T4) ──> RAGAS (T5) ──> Eval Evidence (#10)
Core.md mới ─────┤
Tài liệu nguồn ──┴──> dat ingest (T2) ────┘

Deploy (T2) ──> Live URL (#5) ──> Video demo (T5, #6) ──> Pitch deck (T6, #7)
```

**Chậm ở đâu là nguy hiểm nhất:**

| Rủi ro | Hệ quả | Cách chặn |
|---|---|---|
| Core.md không xong trước 04/08 | `viet` xây sai agent, tuần 3 phải làm lại | Lead viết ngay tuần này |
| Không có tài liệu nguồn | Không bật được RAG, mất luôn deliverable #10 | Chốt nguồn trước 04/08 |
| Deploy dồn tới tuần cuối | Lỗi triển khai không kịp sửa, mất #5 và #6 | Deploy tuần 2, không hoãn |
| Sửa `models/` mà quên `types.ts` | FE/BE lệch nhau lặng lẽ, CI không bắt | Bắt buộc cùng một PR |

---

# Nghi thức hàng tuần

**Thứ Hai — 15 phút:** mỗi người nói task tuần này và cái gì đang chặn mình.

**Hàng ngày:** mỗi người thêm 1 dòng vào `WORKLOG.md`, commit kèm code. Không viết bù cuối tuần — BTC xem git history.

**Thứ Bảy — 30 phút:**
1. Đối chiếu bảng deliverable, đổi màu trạng thái
2. Lead viết `JOURNAL.md`: học được gì · khó ở đâu · quyết định gì · tuần sau làm gì
3. Merge tất cả nhánh cá nhân vào `develop`
4. Chạy `make check` trên `develop`, phải xanh

**Trước mọi lần push:**
```bash
make check                              # hoặc: ruff check src/ tests/ && pytest tests/
git status --ignored --short src/ | grep '!!'   # bắt file bị .gitignore nuốt
```

---

# Quy tắc không được vi phạm

1. **Không bịa số.** Giá, diện tích, tình trạng căn chỉ nêu khi có trong tài liệu hoặc kết quả tool.
2. **Luôn trích nguồn** cho khẳng định lấy từ tài liệu.
3. **Phân quyền lọc tại tầng truy hồi**, không lọc ở giao diện.
4. Không `git push --no-verify`, không sửa/xoá `.ai-log/`.
5. Không merge PR khi CI đỏ
