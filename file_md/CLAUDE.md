# Salemate — Context cho Claude Code

## Dự án là gì
SalesMate: web hỗ trợ nhân viên **Sale** bán căn hộ trong một khu đô thị, có AI
agent hỗ trợ tư vấn. Hai vai trò: `admin` và `sale`. Giao diện giống nhau; admin
có thêm chức năng quản lý. Mockup giao diện home: `home.html`.

## Tech stack (dùng đúng, không đổi nếu chưa hỏi)
- **Frontend:** React. Chỉ gọi backend của dự án — KHÔNG gọi thẳng OpenAI/DB.
- **Backend:** Python + FastAPI.
- **Database:** Supabase (PostgreSQL được quản lý). Kết nối qua `DATABASE_URL`
  (Supabase connection pooler).
- **Lưu trữ ảnh/tài liệu:** Supabase Storage, bucket `apartment-images`.
- **Auth:** JWT, phân quyền theo `role`.
- **Chatbot:** backend proxy OpenAI; sau thay bằng **AI Agent Python** không đổi API.

## Database (QUAN TRỌNG — đọc DATABASE.md)
Chạy trên **Supabase**. Đã có 2 bảng: **`salemate_v1`** (căn hộ) và
**`apartment_images`** (ảnh, liên kết `ma_can`). Cần thêm: `users`, `zones`,
`towers`, `sales_history`, `documents`, (tùy chọn) `chat_messages`.

Lưu ý cột trong `salemate_v1`:
- Tên cột có dấu + khoảng trắng → SQL phải bọc nháy kép: `"Tòa"`, `"Giá"`,
  `"Tình trạng"`…
- `"Giá"` và `"Diện tích"` đang là **text** → dùng cột số `gia_tri`,
  `dien_tich_so` để lọc (xem DATABASE.md phần chỉnh sửa).
- `ma_can` nên là PRIMARY KEY để làm khóa ngoại.

## Biến môi trường (đặt trong `/backend/.env`, KHÔNG commit)
Đây là **mẫu (placeholder)** — điền giá trị thật vào `.env` cục bộ, không ghi vào
file này hay bất kỳ file nào được commit:
```dotenv
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon-key>                 # dùng phía client, an toàn tương đối
SUPABASE_SERVICE_ROLE_KEY=<service-role-key> # CHỈ backend, bí mật tuyệt đối, bỏ qua RLS
SUPABASE_BUCKET=apartment-images
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres
JWT_SECRET=<chuỗi-ngẫu-nhiên-dài>
OPENAI_API_KEY=<openai-key>
```
- Thêm `.env` vào `.gitignore`. Có thể commit một file `/.env.example` chỉ chứa
  các placeholder trên (không có giá trị thật).

## Cấu trúc thư mục đề xuất
```
/backend/app/{core,models,schemas,routers}/  main.py   .env
/frontend/src/{api,components,context,pages}/
/docs/  (spec chi tiết, import bên dưới)
```

## QUY TẮC BẮT BUỘC
1. **Không để secret ở frontend.** `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
   `JWT_SECRET`, `OPENAI_API_KEY` chỉ ở backend, đọc từ `.env`, không hardcode.
   Riêng `SUPABASE_SERVICE_ROLE_KEY` **tuyệt đối chỉ dùng ở backend** (nó bỏ qua
   Row Level Security). Frontend nếu gọi Supabase trực tiếp thì chỉ dùng
   `SUPABASE_ANON_KEY`.
2. **Phân quyền kiểm ở backend**, không chỉ ẩn nút ở frontend. Route admin phải
   có dependency chặn `role != 'admin'`.
3. **Sale chỉ xem lịch sử bán của chính mình.** `sale_id` lấy từ JWT, KHÔNG nhận
   từ client.
4. **Tìm kiếm căn hộ chỉ trả `"Tình trạng" = 'Còn'`.**
5. **Hash mật khẩu** (bcrypt/argon2).
6. Giá lọc trong **0–20 tỷ VND**, dùng cột số `gia_tri`.
7. Endpoint `/api/chat` giữ contract `{message,history} -> {reply}` để sau thay
   OpenAI bằng AI Agent mà frontend không đổi.

## Lệnh dev (điền lại khi đã dựng)
- Backend: `uvicorn app.main:app --reload`
- Frontend: `npm run dev`

## Spec chi tiết
@docs/FEATURES.md
@docs/DATABASE.md
@docs/API.md
@docs/FRONTEND.md
@docs/ROADMAP.md
