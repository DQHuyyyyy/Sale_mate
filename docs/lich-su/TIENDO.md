# TIẾN ĐỘ — SalesMate (backend + frontend)

Cập nhật: 04/08/2026 · Nguồn yêu cầu: [`file_md/`](file_md/) (CLAUDE.md · API.md ·
DATABASE.md · FRONTEND.md · ROADMAP.md · home.html)

---

## 1. Tóm tắt

| Hạng mục | Trạng thái |
|---|---|
| Backend FastAPI — 14 endpoint, khớp `API.md` | ✅ code xong, test xanh |
| Frontend React (Vite) — 10 route, bám mockup `home.html` | ✅ code xong, build xanh |
| SQL migration `001` + `002` + tài khoản admin/sale | ✅ **đã chạy thẳng lên Supabase** ngày 04/08 |
| SQL migration `003` (seed khu/tòa) | ⛔ chưa chạy — xem mục 4 |
| Chạy thật với dữ liệu Supabase | ✅ đăng nhập, tra 100 căn, xem ảnh, lọc tòa/giá/loại căn, thêm căn, ghi nhận bán — tất cả đã chạy thật |
| Ghép AI Agent (giai đoạn 7) | ⛔ chưa làm, đã chừa chỗ cắm |

**Tài khoản đăng nhập** (đổi mật khẩu trước khi nộp bài):

| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| admin | `admin` | `Admin@12345` |
| sale | `sale01` | `Sale@12345` |

**Còn thiếu:** sơ đồ phân khu — cần chạy `003`, nhưng phải chốt danh sách phân
khu trước. Xem mục 4.

---

## 2. Quyết định đã chốt (bạn chọn ngày 04/08)

| Câu hỏi | Chọn |
|---|---|
| Stack frontend | Vite + React + JavaScript, `react-router-dom` |
| Code cũ (`src/`, `CLAUDE.md` gốc — sản phẩm portal BĐS khác) | Để nguyên, `backend/` là app độc lập |
| Quyền chạm database | Chỉ viết file `.sql` + script; tôi **không** kết nối DB thật |
| Tầng truy cập DB | SQL thuần qua `psycopg` 3, không ORM |
| Trang xem tài liệu | Thêm `/documents` + mục "Tài liệu" trên header, mọi tài khoản xem được |
| Bảng `chat_messages` | Chưa ghi — để đến lúc ghép AI Agent |
| Cột số `gia_tri`/`dien_tich_so` | Cột **sinh tự động** từ cột text, không phải parse một lần |
| Xoá tài khoản sale | **Vô hiệu hoá** (`is_active`), không xoá hẳn — giữ lịch sử bán |
| Chỗ đặt chức năng quản lý tài khoản | Gộp vào trang Quản lý Sale, không thêm mục menu mới |
| Khách vãng lai (08/08) | Xem được tìm kiếm, chi tiết căn, phân khu, chatbot. Tài liệu vẫn đóng |
| Chatbot sidebar (08/08) | Sidebar phải 1/3 trang, nội dung co lại còn 2/3 |
| Lệch tên cột `salemate_v1` | Sửa code theo tên cột thật, không đổi database |
| Giá trị đánh dấu đã bán | `'Hết'` (theo tên cột `"Tình trạng (Còn/Hết)"`), không phải `'Đã bán'` |
| Loại căn viết không thống nhất | Chuẩn hoá khi lọc và khi đổ dropdown, dữ liệu gốc giữ nguyên |

---

## 3. Đã làm được

### Giai đoạn 0 — Khởi tạo & database
- [x] `backend/` (FastAPI) và `frontend/` (Vite) dựng mới, độc lập nhau.
- [x] `backend/.env.example` + `frontend/.env.example`; cả hai thư mục đều có
      `.gitignore` chặn `.env`.
- [x] `migrations/001_alter_salemate_v1.sql` — PK `ma_can`, thêm `gia_tri` /
      `dien_tich_so`, parse `"1,8 tỷ"` → `1.800` và `"28m2"` → `28.00`, tạo index.
- [x] `migrations/002_create_tables.sql` — `users`, `zones`, `towers`,
      `sales_history`, `documents`, `chat_messages`, khoá ngoại cho `apartment_images`.
- [x] `migrations/003_seed.sql` — seed `zones` (S, R) và `towers` lấy thẳng từ
      `salemate_v1."Tòa"`, gán khu theo chữ cái đầu.
- [x] `scripts/seed_users.py` — hash bcrypt, in SQL tạo tài khoản (mật khẩu không
      vào repo).
- [ ] ⛔ Chưa chạy các file trên (theo đúng lựa chọn của bạn).

### Giai đoạn 1 — Auth & phân quyền
- [x] `POST /api/auth/login` (bcrypt, thông báo lỗi giống nhau cho sai user và sai
      mật khẩu để không dò được tài khoản), `GET /api/auth/me`.
- [x] `get_current_user` đọc lại user từ DB mỗi request — đổi role hoặc xoá user
      là token cũ mất hiệu lực ngay. `require_admin`, `require_sale`.
- [x] FE: `AuthContext`, trang Login, `ProtectedRoute`, Header + AvatarMenu đổi
      mục theo role (admin **không** có "Lịch sử bán của tôi").

### Giai đoạn 2 — Tìm kiếm căn hộ
- [x] `GET /api/apartments` lọc `tower` / `price_min` / `price_max` / `type`,
      **luôn** chỉ trả `"Tình trạng" = 'Còn'`, lọc giá bằng cột số `gia_tri`, kèm
      ảnh đại diện.
- [x] `GET /api/apartments/{ma_can}` + gallery ảnh theo `sort_order`.
- [x] FE: `SearchFilters` (dropdown tòa lấy từ `/api/towers`, 2 ô giá 0–20, dropdown
      loại căn), `ApartmentCard`, `ApartmentList`, trang chi tiết có gallery.
- [x] Kết quả rỗng hiện đúng câu "Không có căn phù hợp với bộ lọc".

### Giai đoạn 3 — Sơ đồ phân khu
- [x] `GET /api/zones` (kèm danh sách tòa mỗi khu), `GET /api/towers`.
- [x] FE: `ZoneList` + trang `/zones`.

### Giai đoạn 4 — Lịch sử bán
- [x] `GET /api/sales/my-history` — `sale_id` lấy **từ token**, không có tham số
      nào cho client đổi người xem.
- [x] `POST /api/sales` — INSERT `sales_history` + UPDATE `"Tình trạng" = 'Đã bán'`
      trong **một transaction**, căn bị khoá `FOR UPDATE` nên hai sale bấm cùng lúc
      chỉ một người thành công; căn đã bán rồi thì trả 409.
- [x] FE: trang `/my-sales`; nút "Ghi nhận đã bán" đặt trong trang chi tiết căn,
      chỉ hiện với sale và chỉ khi căn còn hàng.

### Giai đoạn 5 — Admin
- [x] `GET /api/users?role=sale`, `GET /api/sales/all` (kèm `full_name` +
      `username`, `ORDER BY sold_at DESC`).
- [x] `POST /api/apartments` — cột text hiển thị (`"Giá"`, `"Diện tích"`) được
      **sinh từ cột số** nên hai bên không bao giờ lệch nhau.
- [x] `POST /api/documents` — nhận file (multipart) hoặc link có sẵn.
- [x] Upload file lên Supabase Storage bằng service role key, chỉ ở backend.
- [x] FE: `/admin/sales`, `/admin/apartments/new`, `/admin/documents/new`.
- [x] **Quản lý tài khoản sale** (thêm ngoài `API.md`, theo yêu cầu ngày 04/08):
      `POST /api/users` tạo tài khoản sale, `PATCH /api/users/{id}` bật/tắt.
      Migration `004_users_is_active.sql` thêm cột `is_active`.
      FE: nút "Thêm tài khoản" + form, cột trạng thái và nút "Vô hiệu hoá /
      Bật lại" ngay trong bảng ở trang Quản lý Sale.
      Backend chặn: tự tắt chính mình, tắt admin khác, tạo admin qua API.
- [x] FE: trang `/documents` + mục "Tài liệu" trên header — `GET /api/documents`,
      lọc theo nhóm, bấm mở file. Trang này **không có trong `FRONTEND.md`**, thêm
      theo quyết định ngày 04/08.

### Giai đoạn 6 — Chatbot
- [x] `POST /api/chat` giữ đúng contract `{message, history} -> {reply}`, gọi
      OpenAI từ backend, prompt cấm bịa giá/diện tích.
- [x] FE: `ChatbotWidget` chữ "S", phóng to/thu nhỏ, giữ lịch sử hội thoại trong
      state và gửi kèm mỗi lượt.

### Mở website cho khách vãng lai (yêu cầu ngày 08/08)
- [x] Backend: `get_optional_user` — có token thì trả user, không thì trả `None`
      thay vì ném lỗi. Gắn vào `/api/apartments` (tìm kiếm + chi tiết),
      `/api/zones`, `/api/towers`, `/api/chat`.
- [x] Vẫn đóng: `/api/documents`, `/api/sales/*`, `/api/users/*`, và mọi thao tác
      ghi (thêm căn hộ, thêm tài liệu, ghi nhận bán).
- [x] `/api/chat` mở public nên thêm hạn mức theo IP: khách 10 lượt/10 phút,
      đã đăng nhập 60 lượt/10 phút, vượt thì trả 429 kèm `Retry-After`.
      Bộ đếm nằm trong bộ nhớ tiến trình — xem giới hạn ở `app/core/ratelimit.py`.
- [x] FE: nút "Đăng nhập" ở góc trên bên phải, đúng chỗ avatar sẽ hiện sau khi
      đăng nhập nên vị trí không nhảy. Đăng nhập xong quay lại đúng trang đang xem.
- [x] FE: mục "Tài liệu" trên nav chỉ hiện khi đã đăng nhập.
- [x] FE: chatbot đổi từ cửa sổ nổi thành **sidebar phải 1/3 trang**; mở ra thì
      nội dung co lại còn 2/3, lưới căn hộ giảm từ 4 cột xuống 3. Dưới 1100px
      sidebar phủ lên thay vì co nội dung.

### Kiểm thử
- [x] 19 test chạy xanh, không chạm DB và không gọi mạng
      (`cd backend && pytest -q`):
  - hash/verify mật khẩu, JWT hết hạn & bị sửa, format giá/diện tích;
  - sale gọi `/api/sales/all` và `/api/users` → **403**;
  - `/api/sales/my-history` luôn dùng `sale_id` trong token, kể cả khi client
    nhét `?sale_id=999`;
  - mọi route đều trả **401** khi không có token.
- [x] `npm run build` xanh.

---

## 4. Còn thiếu

1. **`003_seed.sql`** — seed `zones` và `towers`. Chưa chạy nên trang Sơ đồ phân
   khu trống và dropdown lọc tòa rỗng.
   ⚠️ **Đang chờ bạn.** Dữ liệu thật có **39 tòa** thuộc 8 nhóm chữ cái đầu
   (S, R, H, LD, M, P, PR, ZR), trong khi file chỉ seed 2 khu Sapphire và Ruby →
   30 tòa sẽ có `zone_id` NULL. Cần biết dự án thật có mấy phân khu và tòa nào
   thuộc khu nào.

2. **Tạo bucket `apartment-images`** trên Supabase Storage nếu chưa có — cần cho
   chức năng upload ảnh và tài liệu. Đây là phần duy nhất chưa được thử thật.

3. **Đổi mật khẩu hai tài khoản** trước khi nộp bài.

---

## 5. Chưa làm — nằm ngoài phạm vi đợt này

| Việc | Ghi chú |
|---|---|
| Giai đoạn 7 — ghép AI Agent | Chỉ cần thay hàm `generate_reply` trong `backend/app/services/chat.py`; router và frontend không đổi |
| Lưu hội thoại vào `chat_messages` | Bảng đã tạo, backend cố ý chưa ghi — làm cùng lúc ghép AI Agent |
| Sửa/xoá căn hộ, sửa profile | Không có trong `API.md` |
| Đổi mật khẩu (tự đổi, hoặc admin đặt lại cho sale) | Chưa có. Hiện admin đặt mật khẩu lúc tạo tài khoản rồi bàn giao; quên mật khẩu thì phải sửa thẳng trong DB |
| Phân trang danh sách căn | Backend đã có `limit`/`offset`, frontend chưa dùng (hiện lấy tối đa 100 căn) |
| Test cho route cần DB thật | Cần một database test riêng, chưa dựng |

---

## 6. Việc cần bạn quyết

1. **`docs/FEATURES.md`** được `@import` trong `file_md/CLAUDE.md` nhưng không có
   trong `file_md/`. Nếu file này tồn tại, gửi tôi để đối chiếu — hiện tôi suy
   tính năng từ ROADMAP + FRONTEND + API.
2. **Phân khu của dự án thật.** 39 tòa trong DB không khớp 2 khu Sapphire/Ruby
   trong tài liệu. Cần danh sách khu và tòa nào thuộc khu nào thì mới seed đúng.
3. **Cột `"Ảnh"`** trong `salemate_v1` (giá trị "1. R103", "2. S102") dùng để làm
   gì? Hiện backend bỏ qua, ảnh lấy từ bảng `apartment_images`.

---

## 7. Khó khăn đã gặp và cách xử lý

| Vấn đề | Cách xử lý |
|---|---|
| Cột `salemate_v1` có dấu và khoảng trắng (`"Tòa"`, `"Loại căn (PN, WC) Studio"`) | Viết SQL thuần, bọc nháy kép, gom hằng `APARTMENT_COLUMNS` một chỗ để không lặp và không gõ sai |
| `"Giá"` là text (`"1,8 tỷ"`) không lọc `BETWEEN` được | Migration parse sang `gia_tri`; API lọc bằng cột số, trả cả text lẫn số. Khi client **không** gửi bộ lọc giá thì căn có `gia_tri` NULL vẫn hiện — nếu ràng luôn, căn parse hụt sẽ biến mất im lặng |
| Cột text và cột số dễ lệch khi admin thêm căn | Form chỉ nhập số; backend sinh `"1,8 tỷ"` / `"28m2"` từ số |
| Hai sale cùng bấm bán một căn | `SELECT … FOR UPDATE` + kiểm tra `'Còn'` trong cùng transaction, người sau nhận 409 |
| Upload ảnh mà không lộ service role key | Thêm `POST /api/apartments/{ma_can}/images` (multipart, chỉ admin) — backend đẩy lên Storage rồi lưu `storage_path`. Endpoint này **không có trong `API.md`**, là phần mở rộng |
| **Tên cột thật khác `DATABASE.md`** — `"Loại căn⏎(PN, WC) Studio"` có ký tự xuống dòng, `"Số đỏ"` chứ không phải "Sổ đỏ", `"Tình trạng (Còn/Hết)"` chứ không phải "Tình trạng" | Gom hết tên cột vào `app/core/columns.py`, sửa code theo DB, cập nhật lại `file_md/DATABASE.md`. Không ai được gõ tay tên cột ở chỗ khác |
| Loại căn viết ba kiểu cho cùng một loại | So khớp sau khi bỏ khoảng trắng + hạ chữ thường (`normalize_sql`), dropdown gộp bằng `uniqueTypes()`. Kiểm chứng: lọc `'1 PN, 1WC'` và `'1PN, 1WC'` đều ra 41 căn |
| Chưa chạy `001` thì thiếu cột `gia_tri` → mọi truy vấn căn hộ sập | `app/core/schema.py` dò cột lúc chạy; thiếu thì trả `NULL::numeric` để response giữ nguyên hình dạng, và bộ lọc giá trả 503 kèm hướng dẫn thay vì 500 |
| **Cột `"Giá"` là text** (`'1,8 tỷ'`) nên không lọc `BETWEEN` được | Thêm cột **sinh tự động** `gia_tri` — sửa `"Giá"` thì cột số tự đổi theo, không bao giờ lệch. Xem `file_md/DATABASE.md` mục B |
| Một dòng ghi `'3.55'` (chấm thập phân) trong khi 99 dòng dùng phẩy → parse ra **355 tỷ** | Quy tắc mới: dấu phân tách **cuối cùng** là dấu thập phân. Đọc đúng cả hai kiểu. (Bạn cũng đã sửa dòng đó thành `'3,55 tỷ'`) |
| `'28m2'` parse ra **282 m²** vì đơn vị "m2" có chứa chữ số 2 | Bỏ `[mM][2²]?` trước khi nhặt chữ số. Bẫy này chỉ lộ ra khi chạy trên dữ liệu thật |
| `001` đòi tạo khoá chính trong khi bảng đã có sẵn `salemate_v1_pkey` | Kiểm tra theo **loại** ràng buộc (`contype='p'`), không theo tên. `002` cũng vậy — bản cũ đã lỡ thêm một khoá ngoại trùng lặp vào `apartment_images`, đã gỡ |
| `002` không chạy được khi chưa có `001` (khoá ngoại đòi khoá chính của `salemate_v1`) | Tách hai khoá ngoại xuống cuối file, chỉ thêm khi khoá chính đã tồn tại; chạy lại `002` sau `001` là đủ |
| `psycopg` ghim cứng phiên bản thì máy Python 3.14 cài không được | `requirements.txt` chốt cận dưới (`>=`) thay vì `==` |
| `backend/.venv` hỏng vì bị `python -m venv` tạo đè lúc venv gốc đang bật (config 3.11 nhưng gói `cp314`) | Dựng lại venv bằng đúng Python 3.11. Nhớ `deactivate` venv gốc trước khi làm việc trong `backend/` |
| `backend/.env` có 2 dòng `DATABASE_URL`, dòng placeholder nằm sau nên thắng | Xoá dòng placeholder; siết `.gitignore` thành `.env.*` để bản sao `.env` không lọt vào git |
| Supabase pooler không giữ được prepared statement | Đặt `prepare_threshold=None` khi tạo pool |
| Mockup `home.html` có nút gạt Sale/Admin | Bỏ — đó là công cụ demo. Role thật lấy từ token |

---

## 8. Chạy lại từ đầu

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env          # rồi điền giá trị thật
pytest -q
uvicorn app.main:app --reload # http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Chi tiết trong [`backend/README.md`](backend/README.md) và
[`frontend/README.md`](frontend/README.md).
