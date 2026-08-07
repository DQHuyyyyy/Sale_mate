# SalesMate — Backend (FastAPI)

cd E:\VSCSTD\VIN\P-055
.venv\Scripts\activate
cd interface\backend
uvicorn app.main:app --reload --port 8000
# nếu ai đó đang bật thì dùng lệnh để tắt: 
Stop-Process -Id <PID> -Force
## Chạy lần đầu

```bash
cd interface/backend
python -m venv .venv
.venv\Scripts\activate          # Windows;  Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload
```

Mở http://localhost:8000/docs — Swagger có sẵn nút **Authorize** để dán token.
Kiểm tra nhanh: `GET /api/health`.

## Cấu hình

Backend đọc **`.env` ở gốc repo**, không có file `.env` riêng. Thư mục này từng
có một file như vậy nhưng nó chỉ chứa placeholder và ghi đè mất giá trị thật ở
`.env` gốc, nên đã bỏ.

Chưa có `.env` thì: `cp .env.example .env` ở gốc repo rồi điền. Riêng
`JWT_SECRET` phải dài ≥32 ký tự, sinh bằng:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Thiếu biến bắt buộc thì backend **từ chối khởi động** và in ra thiếu cái gì —
không chạy tiếp với cấu hình hỏng.

## Dựng database (chạy một lần, theo thứ tự)

Vào Supabase → **SQL Editor**, dán từng file:

| Thứ tự | File | Làm gì |
|---|---|---|
| 1 | `migrations/001_alter_salemate_v1.sql` | PK `ma_can`, thêm `gia_tri`/`dien_tich_so`, parse từ cột text, tạo index |
| 2 | `migrations/002_create_tables.sql` | `users`, `zones`, `towers`, `sales_history`, `documents`, `chat_messages` |
| 3 | `migrations/003_seed.sql` | Seed `zones` + `towers` (tòa lấy thẳng từ dữ liệu thật) |
| 4 | `migrations/004_users_is_active.sql` | Cột `is_active` để vô hiệu hoá tài khoản sale |

Sau bước 1, chạy 2 câu KIỂM TRA ghi trong file để xem còn dòng nào parse hụt giá
hoặc diện tích không — dòng đó sẽ không lọt bộ lọc giá.

Tạo tài khoản (mật khẩu hash bằng bcrypt, không nằm trong repo):

```bash
python scripts/seed_users.py     # nhập username/mật khẩu → in ra SQL để dán vào Supabase
```

## Cấu trúc

```
app/
├── core/       config · db (pool psycopg) · security (bcrypt + JWT) · deps (phân quyền)
├── schemas/    Pydantic — hợp đồng dữ liệu với frontend
├── routers/    auth · apartments · zones · sales · users · documents · chat
├── services/   storage (Supabase Storage) · chat (lõi chatbot, sau thay bằng AI Agent)
└── main.py
migrations/     SQL chạy tay trên Supabase
scripts/        seed_users.py
tests/          test không chạm DB, không gọi mạng
```

## Quy tắc không được vi phạm

1. **Secret chỉ ở backend.** `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
   `JWT_SECRET`, `OPENAI_API_KEY` đọc từ `.env`, không hardcode, không trả ra API.
2. **Phân quyền kiểm ở backend.** Route admin phải có `Depends(require_admin)`.
3. **`sale_id` lấy từ token**, không bao giờ nhận từ query/body.
4. **Tìm kiếm chỉ trả `"Tình trạng" = 'Còn'`.**
5. **Lọc giá dùng cột số `gia_tri`**, khoảng hợp lệ 0–20 tỷ.
6. Cột tiếng Việt trong `salemate_v1` phải bọc nháy kép: `"Tòa"`, `"Giá"`.
7. `/api/chat` giữ nguyên contract `{message, history} -> {reply}`.

## Test

```bash
pytest -q
```

Test hiện chỉ phủ hash mật khẩu, JWT và format giá/diện tích — không cần DB, không
gọi mạng. Test cho route cần một database test riêng (xem `TIENDO.md`).
