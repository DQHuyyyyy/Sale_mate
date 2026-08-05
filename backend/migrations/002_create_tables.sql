-- ============================================================
-- 002 — Các bảng cần thêm
--
-- File này CHỈ tạo bảng mới, KHÔNG đụng gì tới salemate_v1 và dữ liệu căn hộ.
-- Chạy được ngay cả khi chưa chạy 001.
--
-- Hai khoá ngoại trỏ về salemate_v1(ma_can) cần khoá chính do 001 tạo, nên ở
-- cuối file chúng chỉ được thêm khi khoá chính đã tồn tại. CHẠY LẠI FILE NÀY
-- SAU KHI CHẠY 001 để bổ sung hai khoá ngoại đó. Chạy lại nhiều lần vẫn an toàn.
-- ============================================================

-- users — tài khoản admin/sale. id dùng làm sale_id.
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,              -- bcrypt
    full_name     VARCHAR(100) NOT NULL,
    role          VARCHAR(10) NOT NULL CHECK (role IN ('admin','sale')),
    phone         VARCHAR(20),
    email         VARCHAR(100),
    avatar_url    TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- zones — phân khu, dùng cho trang "Sơ đồ phân khu"
CREATE TABLE IF NOT EXISTS zones (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    image_url   TEXT
);

-- towers — nối "Tòa" của salemate_v1 với zones
CREATE TABLE IF NOT EXISTS towers (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20) UNIQUE NOT NULL,          -- khớp salemate_v1."Tòa"
    name        VARCHAR(100),
    zone_id     INTEGER REFERENCES zones(id),
    description TEXT
);

-- sales_history — lịch sử bán
-- Khoá ngoại ma_can -> salemate_v1 được thêm ở cuối file, sau khi 001 tạo khoá chính.
CREATE TABLE IF NOT EXISTS sales_history (
    id             SERIAL PRIMARY KEY,
    ma_can         TEXT NOT NULL,
    sale_id        INTEGER NOT NULL REFERENCES users(id),
    customer_name  VARCHAR(100),
    customer_phone VARCHAR(20),
    sold_price     NUMERIC(12,3),                     -- giá bán thực tế, tỷ VND
    sold_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sales_sale ON sales_history(sale_id);
CREATE INDEX IF NOT EXISTS idx_sales_time ON sales_history(sold_at DESC);

-- documents — tài liệu do admin thêm
CREATE TABLE IF NOT EXISTS documents (
    id            SERIAL PRIMARY KEY,
    title         VARCHAR(200) NOT NULL,
    description   TEXT,
    file_url      TEXT,
    drive_file_id TEXT,
    file_name     VARCHAR(255),
    category      VARCHAR(50),
    uploaded_by   INTEGER REFERENCES users(id),
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_time ON documents(created_at DESC);

-- chat_messages — tuỳ chọn, lưu hội thoại chatbot.
-- Backend hiện KHÔNG ghi bảng này (xem TIENDO.md, mục "Chưa làm").
CREATE TABLE IF NOT EXISTS chat_messages (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id),
    role       VARCHAR(10) CHECK (role IN ('user','assistant')),
    content    TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_images_ma_can ON apartment_images(ma_can, sort_order);

-- ------------------------------------------------------------
-- Khoá ngoại về salemate_v1(ma_can)
-- Chỉ thêm được khi ma_can đã là khoá chính (do 001 tạo). Chưa chạy 001 thì
-- khối này bỏ qua trong im lặng — chạy lại file sau khi có 001 để bổ sung.
-- ------------------------------------------------------------
DO $$
DECLARE
    co_khoa_chinh BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'salemate_v1' AND c.contype IN ('p', 'u')
    ) INTO co_khoa_chinh;

    IF NOT co_khoa_chinh THEN
        RAISE NOTICE 'Bỏ qua khoá ngoại: salemate_v1 chưa có khoá chính. Chạy 001 rồi chạy lại file này.';
        RETURN;
    END IF;

    -- apartment_images đã có sẵn khoá ngoại `apartment_images_ma_can_fkey` trong
    -- database thật. Kiểm theo BẢNG + LOẠI, không kiểm theo tên, để khỏi thêm
    -- một khoá ngoại trùng lặp.
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'apartment_images' AND c.contype = 'f'
    ) THEN
        ALTER TABLE apartment_images
            ADD CONSTRAINT fk_images_ma_can
            FOREIGN KEY (ma_can) REFERENCES salemate_v1(ma_can) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'sales_history' AND c.contype = 'f'
          AND pg_get_constraintdef(c.oid) LIKE '%salemate_v1%'
    ) THEN
        ALTER TABLE sales_history
            ADD CONSTRAINT fk_sales_ma_can
            FOREIGN KEY (ma_can) REFERENCES salemate_v1(ma_can);
    END IF;
END $$;
