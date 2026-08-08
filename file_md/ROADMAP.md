# ROADMAP — Lộ trình xây dựng

## Giai đoạn 0 — Khởi tạo & database
- [ ] Tạo repo: `/backend`, `/frontend`, `/docs`.
- [ ] Backend FastAPI + kết nối **Supabase** (`DATABASE_URL` pooler từ `.env`).
- [ ] Cấu hình Supabase Storage bucket `apartment-images` + client backend dùng
      `SUPABASE_SERVICE_ROLE_KEY`. Tạo `.env` (gitignore) và `.env.example`.
- [ ] `salemate_v1`: thêm PRIMARY KEY `ma_can`; thêm cột số `gia_tri`,
      `dien_tich_so` và parse từ cột text.
- [ ] Tạo bảng mới: `users`, `zones`, `towers`, `sales_history`, `documents`.
- [ ] Seed: zones (S, R…), map `towers` → zone, 1 admin + vài sale.
- [ ] Frontend: khởi tạo React, lớp `src/api`, bê phong cách từ `home.html`.

## Giai đoạn 1 — Auth & phân quyền
- [ ] `POST /api/auth/login`, `GET /api/auth/me`, hash mật khẩu.
- [ ] Dependency `get_current_user`, `require_admin`.
- [ ] FE: `AuthContext`, Login, `ProtectedRoute`, Header + AvatarMenu theo role.

## Giai đoạn 2 — Tìm kiếm căn hộ (lõi)
- [ ] `GET /api/apartments` lọc `tower`,`price_min/max` (cột `gia_tri`),`type`;
      chỉ `'Còn'`; kèm ảnh từ `apartment_images`.
- [ ] `GET /api/apartments/{ma_can}` + gallery ảnh.
- [ ] FE: `SearchFilters`, `ApartmentCard`, `ApartmentList`, `ApartmentDetail`.

## Giai đoạn 3 — Sơ đồ phân khu
- [ ] `GET /api/zones` (+ `GET /api/towers` cho dropdown).
- [ ] FE: `ZoneList`, trang Zones.

## Giai đoạn 4 — Lịch sử bán (Sale)
- [ ] `GET /api/sales/my-history` (lọc `sale_id` từ token).
- [ ] `POST /api/sales` (INSERT + đổi trạng thái căn 'Đã bán').
- [ ] FE: trang MySales. Kiểm thử: sale A không xem được của sale B.

## Giai đoạn 5 — Admin
- [ ] `GET /api/users?role=sale`; `GET /api/sales/all` (tên+username, `sold_at DESC`).
- [ ] `POST /api/apartments`, `POST /api/documents` (chỉ admin).
- [ ] FE: Quản lý Sale, Add Apartment, Add Document.

## Giai đoạn 6 — Chatbot
- [ ] `POST /api/chat` proxy OpenAI, contract `{message,history} -> {reply}`.
- [ ] FE: `ChatbotWidget` chữ "S", phóng to/thu nhỏ.

## Giai đoạn 7 — Ghép AI Agent
- [ ] Thay lõi `/api/chat` từ OpenAI sang AI Agent Python (FE không đổi).

## Kiểm thử xuyên suốt
- [ ] Không có secret nào ở frontend.
- [ ] Route admin bị chặn khi gọi bằng tài khoản sale.
- [ ] `my-history` không lộ dữ liệu người khác qua sửa param.
