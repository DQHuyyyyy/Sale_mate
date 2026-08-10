# DATABASE — Supabase / PostgreSQL

Database chạy trên **Supabase**. Kết nối qua biến môi trường trong
`/backend/.env` (KHÔNG hardcode, KHÔNG commit — dùng placeholder):
```dotenv
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres
```
- Đây là chuỗi kết nối tới **Supabase connection pooler** (không phải localhost).
- Ảnh/tài liệu lưu ở **Supabase Storage**, bucket `apartment-images`
  (biến `SUPABASE_BUCKET`). Xem thêm mục ảnh bên dưới.

Có **2 bảng đã tồn tại** (`salemate_v1`, `apartment_images`) và các bảng **cần
thêm** (`users`, `zones`, `towers`, `sales_history`, `documents`, `chat_messages`).

---

## A. Bảng đã có

### salemate_v1  (căn hộ)
Tên cột hiện tại có dấu tiếng Việt và khoảng trắng → khi viết SQL phải bọc trong
dấu nháy kép, ví dụ `"Tòa"`, `"Giá"`.

> **Đã đối chiếu với database thật ngày 04/08/2026.** Ba tên cột trong bản trước
> của tài liệu này SAI so với DB, đã sửa lại bên dưới. Code lấy tên cột từ
> `backend/app/core/columns.py` — đừng gõ tay ở chỗ khác.

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| `ma_can` | text | Mã căn (VOP103…). **Nên đặt PRIMARY KEY / UNIQUE** để làm khóa ngoại. |
| `"Tòa"` | text | Tòa. Dữ liệu thật có 39 tòa: S1, S2, S101…S219, R101, R103, R105, H1, H2, LD1, LD3, M1, M3, P3, P4, PR1, PR5, ZR1. |
| `"Tầng"` | int8 | Tầng. |
| `"Số phòng"` | int8 | Số/mã phòng trên tầng (vd tầng 20 → 2006). Không phải số phòng ngủ. |
| `"Loại căn⏎(PN, WC) Studio"` | text | ⚠️ Tên cột có **ký tự xuống dòng** giữa "căn" và "(PN". Giá trị viết không thống nhất: `'1 PN, 1WC'`, `'1PN, 1 WC'`, `'1PN, 1WC'` là cùng một loại → so khớp sau khi bỏ khoảng trắng. |
| `"Diện tích"` | text | Dạng "28m2", "34.7m2" (dấu **chấm** thập phân) — **nên thêm cột số** để lọc. |
| `"Hướng phong thủy"` | text | Hướng. |
| `"View"` | text | Mô tả view. |
| `"Số đỏ"` | text | ⚠️ Là **"Số đỏ"**, không phải "Sổ đỏ". Giá trị "Sẵn sổ"… |
| `"Giá"` | text | Dạng "1,8 tỷ", "2,650 tỷ" (dấu **phẩy** thập phân) — **nên thêm cột số** để lọc khoảng giá. |
| `"Nội thất"` | text | Mô tả nội thất. |
| `"Tình trạng (Còn/Hết)"` | text | ⚠️ Tên cột có phần "(Còn/Hết)". Giá trị: `'Còn'` / `'Hết'`. Tìm kiếm chỉ lấy 'Còn'; bán xong ghi 'Hết'. |
| `"Ảnh"` | text | Cột có sẵn trong DB, không rõ mục đích. Giá trị dạng "1. R103", "2. S102" — **không phải URL**. Ảnh thật nằm ở bảng `apartment_images`. Backend không dùng cột này. |

### apartment_images  (ảnh căn hộ)
| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| `id` | int8 | PK. |
| `ma_can` | text | FK → `salemate_v1.ma_can`. |
| `image_url` | text | URL ảnh. Có thể là link cũ (Google Drive) hoặc public URL từ Supabase Storage. |
| `drive_file_id` | text | ID file Google Drive (dữ liệu cũ). |
| `file_name` | text | Tên file (IMG_xxxx.JPG). |
| `storage_path` | text | Đường dẫn object trong bucket `apartment-images` (vd `VOP103/img1.jpg`). Dùng cho ảnh lưu trên Supabase Storage. |
| `sort_order` | int4 | Thứ tự ảnh (0,1,2…). |
| `created_at` | timestamptz | Thời điểm tạo. |

> **Ảnh mới** (khi admin thêm căn hộ) nên upload lên **Supabase Storage** bucket
> `apartment-images`, lưu đường dẫn vào `storage_path`, rồi sinh public URL (hoặc
> signed URL) để hiển thị. Backend upload bằng `SUPABASE_SERVICE_ROLE_KEY`.

---

## B. Chỉnh sửa đã làm cho `salemate_v1`  ✅ đã chạy 04/08/2026

Khóa chính: **đã có sẵn** từ trước (`salemate_v1_pkey PRIMARY KEY (ma_can)`),
không phải thêm.

Hai cột số là **cột sinh tự động** (`GENERATED ALWAYS AS … STORED`), không phải
cột thường parse một lần:

```sql
ALTER TABLE salemate_v1 ADD COLUMN gia_tri      NUMERIC(12,3) GENERATED ALWAYS AS (…) STORED;
ALTER TABLE salemate_v1 ADD COLUMN dien_tich_so NUMERIC(8,2)  GENERATED ALWAYS AS (…) STORED;
```

Biểu thức đầy đủ trong `backend/migrations/001_alter_salemate_v1.sql`.

**Vì sao chọn cột sinh tự động:** cột text là nguồn sự thật duy nhất. Sửa `"Giá"`
trong Supabase thì `gia_tri` tự đổi theo trong cùng câu UPDATE — không bao giờ
lệch, không phải nhớ chạy lại script parse. Đổi lại, ứng dụng **không được ghi**
vào hai cột này; muốn sửa số thì sửa cột text.

Hai cái bẫy trong biểu thức parse, đều đã xử lý:

1. Dữ liệu dùng lẫn dấu phẩy và dấu chấm thập phân (`'3,55 tỷ'` và `'34.7m2'`)
   → quy tắc: dấu phân tách **cuối cùng** là dấu thập phân.
2. Đơn vị `"m2"` **có chứa chữ số 2** → phải bỏ đơn vị trước khi nhặt chữ số,
   nếu không `'28m2'` thành 282 m².

Kết quả trên 100 dòng thật: giá 1,800–6,400 tỷ; diện tích 27,00–98,40 m²; không
dòng nào parse hụt.

> Từ nay: tìm kiếm/lọc dùng `gia_tri`, `dien_tich_so`; cột text giữ để hiển thị.

---

## C. Bảng cần THÊM

### users  (tài khoản admin/sale)
Phân biệt vai trò bằng `role`. `id` dùng làm `sale_id`.
```sql
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt/argon2
    full_name     VARCHAR(100) NOT NULL,
    role          VARCHAR(10) NOT NULL CHECK (role IN ('admin','sale')),
    phone         VARCHAR(20),
    email         VARCHAR(100),
    avatar_url    TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);
```

### zones  (phân khu — cho "Sơ đồ phân khu")
```sql
CREATE TABLE zones (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE,        -- 'S', 'R'…
    name        VARCHAR(100) NOT NULL,     -- 'Phân khu Sapphire'
    description TEXT,                       -- text mô tả khu
    image_url   TEXT
);
```

### towers  (tòa → thuộc phân khu)
Nối tòa của `salemate_v1` với `zones`, để lọc căn theo khu và dựng sơ đồ.
```sql
CREATE TABLE towers (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE NOT NULL,   -- khớp salemate_v1."Tòa"
    name        VARCHAR(100),
    zone_id     INTEGER REFERENCES zones(id),
    description TEXT
);
```

### sales_history  (lịch sử bán)
Nền tảng cho "Lịch sử bán của tôi" (Sale) và "Căn đã bán toàn hệ thống" (Admin).
```sql
CREATE TABLE sales_history (
    id             SERIAL PRIMARY KEY,
    ma_can         TEXT NOT NULL REFERENCES salemate_v1(ma_can),
    sale_id        INTEGER NOT NULL REFERENCES users(id),
    customer_name  VARCHAR(100),
    customer_phone VARCHAR(20),
    sold_price     NUMERIC(12,3),                 -- giá bán thực tế (tỷ VND)
    sold_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_sales_sale ON sales_history(sale_id);
CREATE INDEX idx_sales_time ON sales_history(sold_at DESC);
```
Khi bán 1 căn: INSERT vào `sales_history` **và** UPDATE
`salemate_v1."Tình trạng (Còn/Hết)" = 'Hết'`.

### documents  (tài liệu admin thêm)
```sql
CREATE TABLE documents (
    id            SERIAL PRIMARY KEY,
    title         VARCHAR(200) NOT NULL,
    description   TEXT,
    file_url      TEXT,                    -- public/signed URL từ Supabase Storage
    drive_file_id TEXT,                     -- (tùy chọn, dữ liệu cũ nếu có)
    file_name     VARCHAR(255),
    category      VARCHAR(50),             -- 'Pháp lý','Bảng giá','Chính sách'…
    uploaded_by   INTEGER REFERENCES users(id),
    created_at    TIMESTAMPTZ DEFAULT now()
);
```

### chat_messages  (tùy chọn — lưu hội thoại chatbot)
Hữu ích khi ghép AI Agent. Chưa cần cũng được.
```sql
CREATE TABLE chat_messages (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    role       VARCHAR(10) CHECK (role IN ('user','assistant')),
    content    TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## D. Sơ đồ quan hệ
- `apartment_images.ma_can` → `salemate_v1.ma_can`
- `salemate_v1."Tòa"` → `towers.code` → `towers.zone_id` → `zones.id`
- `sales_history.ma_can` → `salemate_v1.ma_can`
- `sales_history.sale_id` → `users.id`  (dùng lọc "căn của tôi")
- `documents.uploaded_by` → `users.id`
