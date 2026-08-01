# Worklog — Team P-055

> Ghi lại tất cả công việc đã làm theo ngày, người thực hiện và kết quả.

---

## 2026-07-29

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Viet | Thiết lập repository P-055 trên máy cá nhân | ✅ Done | Repository đã sẵn sàng để phát triển | — |
| Viet | Tạo nhánh làm việc cá nhân và kết nối với GitHub | ✅ Done | Nhánh `viet` đã được tạo và push lên `origin/viet` | — |
| Viet | Cấu hình hook ghi nhận lịch sử làm việc với AI | ✅ Done | Prompt được ghi vào `.ai-log/session.jsonl`; hook hoạt động trên Windows | — |

**Tổng kết ngày:** Hoàn tất thiết lập ban đầu cho repository P-055. Nhánh `viet` đã có trên GitHub và môi trường ghi AI log đã hoạt động.

---

## 2026-08-01

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Viet | Xử lý dữ liệu tồn kho căn hộ (CSV + ảnh) thành tài liệu RAG | ✅ Done | `src/data/sources/inventory.py` — nạp 100/100 căn, gắn ảnh đúng folder, loại giá/tình trạng khỏi text embed (tránh sai lệch với tool tra tồn kho); có test | — |
| Viet | Crawl tin đăng Vinhomes Ocean Park trên batdongsan.com.vn | ✅ Done | Thử crawl tự động — bị Cloudflare chặn (`cf-mitigated: challenge`), không né tránh; chuyển sang thu thập thủ công 33 trang chi tiết + viết `src/data/crawling/batdongsan.py` xử lý hàng loạt (giá, diện tích, pháp lý, mô tả, ảnh, nguồn) — 33/33 parse đúng | — |
| Viet | Dựng pipeline ingest & chứng minh RAG chạy đầu-cuối | ✅ Done | `scripts/ingest_inventory.py`, `scripts/ingest_batdongsan.py`, `scripts/chat_demo_rag.py` — agent thật trả lời đúng kèm trích dẫn nguồn từ dữ liệu đã crawl | — |
| Viet | Viết test cho toàn bộ phần trên | ✅ Done | 69/69 test pass, `ruff check`/`format` sạch, coverage 80% | — |

**Tổng kết ngày:** Hoàn thành phần "crawl data và xử lý data cho RAG" do huy giao. Dữ liệu (tồn kho + tin đăng BĐS thật) đã sẵn sàng và chứng minh chạy được qua demo agent có trích nguồn. Còn lại: bật `ENABLE_RAG` trong `bootstrap.py`, chuyển Qdrant, và hiển thị ảnh/nguồn trong widget — cần team quyết định và phối hợp (agent + frontend), không thuộc phạm vi việc này.

---

<!--
Mẫu cho ngày làm việc tiếp theo:

## YYYY-MM-DD

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Tên | Mô tả công việc | 🔄 WIP | Tiến độ hoặc kết quả | 1.5h |

**Tổng kết ngày:** Tóm tắt tiến độ chung trong 1–2 câu.

---
-->
