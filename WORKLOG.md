# Worklog — Team P-055

> Ghi lại tất cả công việc đã làm theo ngày. Ai làm gì, kết quả gì.

---

## 2026-07-29

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| dat | Clone repo team, checkout code template (commit `663f203`) | ✅ Done | Working tree sạch trên máy local | 0.5h |
| dat | Tạo branch làm việc `dat`, đặt upstream `origin/dat` | ✅ Done | Branch `dat` → `origin/dat`, đã có commit riêng (đi trước `main` 1 commit) | 0.25h |
| dat | Tạo virtualenv `venv/` | ✅ Done | `venv/` — Python 3.14.6 | 0.5h |
| dat | Cài dependencies từ `requirements.txt` | ❌ Blocked | `venv/` mới chỉ có `pip`; `venv` đang là Python 3.14 trong khi Dockerfile + CI dùng 3.11 → cần tạo lại venv bằng 3.11 | 0.25h |
| dat | Cấu hình `.env`: điền `OPENAI_API_KEY` + `AI_LOG_API_KEY` (key riêng từ link mời BTC) | ✅ Done | `.env` đã điền, không commit (có trong `.gitignore`) | 0.25h |
| dat | Điền `LANGCHAIN_API_KEY` cho LangSmith tracing (Deliverable #4) | 🔄 WIP | Vẫn còn placeholder `your-langsmith-key-here` | - |
| dat | Cài AI logging hook trên Windows (`scripts/setup_hooks.ps1`) | ✅ Done | `.git/hooks/pre-push` đã cài, `bash -n` pass | 0.25h |
| dat | Fix `setup_hooks.ps1`: hook bị BOM UTF-8 + CRLF làm hỏng shebang trên Git Bash | ✅ Done | Đã đổi sang ghi UTF-8 no-BOM + LF; đã commit và push lên `origin/dat` | 0.5h |

**Tổng kết ngày:** Xong bước 1 và 3 của Quick Start — repo đã clone, branch cá nhân `dat` đã tạo và track remote, `.env` đã điền key thật, AI usage logging hook chạy được. Bước 2 chưa xong: `venv/` còn rỗng và sai phiên bản Python (3.14 thay vì 3.11 như CI/Docker). Việc tiếp theo: tạo lại venv bằng Python 3.11 → `pip install -r requirements.txt` → chạy `pytest` và `uvicorn src.main:app --reload --port 8000` để kiểm tra template, rồi vào chương 3 — thiết kế kiến trúc.

---

## [YYYY-MM-DD]

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| | | | | |

**Tổng kết ngày:**

---

<!-- Format: copy block trên cho mỗi ngày làm việc -->
