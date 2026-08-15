# RUN.md — Chạy dự án trên máy mình

Hệ thống gồm **3 service chạy song song**, mỗi cái một terminal riêng. Cả
`interface/backend` và `src/` (lõi AI) đọc **chung một file `.env`** ở gốc
repo — xem [`.env.example`](.env.example) để biết cần điền gì.

## Cách 1 — dùng `make` (khuyên dùng, gõ ít hơn)

Windows: `make` không có sẵn, cần cài rồi thêm vào PATH trước — xem mục
"Cài `make` trên Windows" bên dưới nếu lệnh báo
`'make' is not recognized...`.

```bash
# Terminal 1 — Lõi AI (agent + RAG)
make run-ai              # http://localhost:8001/docs

# Terminal 2 — API sản phẩm (auth, tồn kho, khu/toà, chat bridge)
make run-api              # http://localhost:8000/docs

# Terminal 3 — Frontend
make fe                    # http://localhost:5173
```

## Cách 2 — lệnh gốc, không cần `make`

Kích hoạt `.venv` trước (`.venv\Scripts\activate` trên Windows,
`source .venv/bin/activate` trên macOS/Linux), rồi:

```powershell
# Terminal 1 — Lõi AI
python -m uvicorn src.main:app --reload --port 8001

# Terminal 2 — API sản phẩm
cd interface\backend
python -m uvicorn app.main:app --reload --port 8000

# Terminal 3 — Frontend
cd interface\frontend
npm run dev
```

Mở `http://localhost:5173`, chat qua widget góc dưới phải. Frontend gọi
`/api/*` → Vite proxy sang `:8000` (API sản phẩm) → cầu `/api/chat` gọi tiếp
sang `:8001` (lõi AI) qua biến `AI_CORE_URL`.

Chưa có `OPENAI_API_KEY` hợp lệ thì lõi AI **vẫn chạy** — tự rơi về LLM giả
lập, widget vẫn stream chữ, chỉ là nội dung mẫu.

## Cài đặt lần đầu

```bash
python3.11 -m venv .venv
.venv\Scripts\activate            # Windows; macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
pip install -r interface\backend\requirements.txt -r interface\backend\requirements-dev.txt
cd interface\frontend; npm install; cd ..\..

copy .env.example .env            # rồi điền OPENAI_API_KEY, JWT_SECRET...
```

## Hạ tầng (tuỳ chọn — không bắt buộc để dev)

Mặc định hệ thống dùng vector store trong bộ nhớ, không cần Qdrant/Postgres
thật để chạy. Cần dữ liệu RAG thật thì xem mục "Nạp dữ liệu RAG" ở
[`README.md`](README.md).

```bash
make infra          # Qdrant :6333 + Postgres :5432 (cần Docker)
```

## Cài `make` trên Windows

Sau khi cài (Chocolatey `choco install make`, hoặc Scoop `scoop install make`,
hoặc qua Git Bash/WSL đã có sẵn), thêm thư mục chứa `make.exe` vào biến môi
trường `PATH`, mở lại terminal. Không muốn cài thì dùng thẳng Cách 2 ở trên —
tương đương hoàn toàn, không thiếu chức năng gì.
