-- ============================================================
-- 001 — Chỉnh bảng đã có: salemate_v1
-- Chạy trong Supabase → SQL Editor. Chạy lại nhiều lần vẫn an toàn.
--
-- Chỉ THÊM khoá chính và hai cột số. Không xoá, không sửa dữ liệu sẵn có.
-- ============================================================

-- ------------------------------------------------------------
-- 1) Khoá chính ma_can, để sales_history / apartment_images tham chiếu
--
-- Thực tế database đã có sẵn `salemate_v1_pkey PRIMARY KEY (ma_can)`, nên khối
-- này thường không làm gì. Kiểm tra theo LOẠI ràng buộc chứ không theo tên —
-- kiểm theo tên sẽ đòi tạo khoá chính thứ hai và câu lệnh nổ.
-- ------------------------------------------------------------
-- Kiểm tra trùng mã trước (phải trả 0 dòng):
--   SELECT ma_can, count(*) FROM salemate_v1 GROUP BY ma_can HAVING count(*) > 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'salemate_v1' AND c.contype = 'p'
    ) THEN
        ALTER TABLE salemate_v1 ALTER COLUMN ma_can SET NOT NULL;
        ALTER TABLE salemate_v1 ADD CONSTRAINT pk_salemate PRIMARY KEY (ma_can);
    END IF;
END $$;

-- ------------------------------------------------------------
-- 2) Hai cột số để lọc — SINH TỰ ĐỘNG từ cột text
--
-- Cột text ("Giá", "Diện tích") vẫn là nguồn sự thật duy nhất và giữ nguyên để
-- hiển thị. Cột số chỉ là bản dịch, Postgres tự tính lại mỗi khi cột text đổi
-- nên hai bên KHÔNG BAO GIỜ lệch nhau — không phải nhớ chạy lại script parse.
--
-- Quy tắc đọc số: bỏ mọi ký tự không phải chữ số hoặc dấu phân tách, rồi coi
-- dấu phân tách CUỐI CÙNG là dấu thập phân. Nhờ vậy đọc đúng cả "1,8 tỷ"
-- (phẩy thập phân) lẫn "3.55" (chấm thập phân) — dữ liệu thật có cả hai kiểu.
-- Có chữ "triệu" thì chia 1000 để quy về tỷ. Không đọc được thì trả NULL,
-- không làm hỏng câu lệnh.
-- ------------------------------------------------------------

DO $$
DECLARE
    trang_thai TEXT;
BEGIN
    -- gia_tri (tỷ VND)
    SELECT is_generated INTO trang_thai
    FROM information_schema.columns
    WHERE table_name = 'salemate_v1' AND column_name = 'gia_tri';

    IF trang_thai IS NULL THEN
        ALTER TABLE salemate_v1 ADD COLUMN gia_tri NUMERIC(12,3)
        GENERATED ALWAYS AS (
            CASE
                WHEN "Giá" IS NULL OR "Giá" !~ '[0-9]' THEN NULL
                ELSE (
                    replace(replace(
                        regexp_replace(regexp_replace("Giá", '[^0-9,.]', '', 'g'),
                                       '[,.][0-9]*$', ''),
                    ',', ''), '.', '')
                    || '.' ||
                    coalesce(
                        substring(regexp_replace("Giá", '[^0-9,.]', '', 'g')
                                  from '[,.]([0-9]+)$'),
                        '0')
                )::numeric
                / (CASE WHEN strpos("Giá", 'triệu') > 0 THEN 1000 ELSE 1 END)
            END
        ) STORED;
    ELSIF trang_thai = 'NEVER' THEN
        RAISE EXCEPTION
            'Cột gia_tri đang là cột thường, không phải cột sinh tự động. Kiểm tra dữ liệu rồi chạy: ALTER TABLE salemate_v1 DROP COLUMN gia_tri; sau đó chạy lại file này.';
    END IF;

    -- dien_tich_so (m²)
    SELECT is_generated INTO trang_thai
    FROM information_schema.columns
    WHERE table_name = 'salemate_v1' AND column_name = 'dien_tich_so';

    -- CHÚ Ý: phải bỏ đơn vị "m2"/"m²" TRƯỚC khi nhặt chữ số, vì "m2" có chứa
    -- chữ số 2 — giữ lại thì "28m2" thành 282 m².
    IF trang_thai IS NULL THEN
        ALTER TABLE salemate_v1 ADD COLUMN dien_tich_so NUMERIC(8,2)
        GENERATED ALWAYS AS (
            CASE
                WHEN "Diện tích" IS NULL OR "Diện tích" !~ '[0-9]' THEN NULL
                ELSE (
                    replace(replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace("Diện tích", '[mM][2²]?', '', 'g'),
                                '[^0-9,.]', '', 'g'),
                            '[,.][0-9]*$', ''),
                    ',', ''), '.', '')
                    || '.' ||
                    coalesce(
                        substring(
                            regexp_replace(
                                regexp_replace("Diện tích", '[mM][2²]?', '', 'g'),
                                '[^0-9,.]', '', 'g')
                            from '[,.]([0-9]+)$'),
                        '0')
                )::numeric
            END
        ) STORED;
    ELSIF trang_thai = 'NEVER' THEN
        RAISE EXCEPTION
            'Cột dien_tich_so đang là cột thường. Chạy: ALTER TABLE salemate_v1 DROP COLUMN dien_tich_so; rồi chạy lại file này.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 3) KIỂM TRA — chạy sau khi thêm cột.
--    Dòng nào hiện ra là dòng ghi giá/diện tích sai định dạng, sửa lại cột text
--    thì cột số tự đúng theo.
-- ------------------------------------------------------------
-- SELECT ma_can, "Giá", gia_tri FROM salemate_v1
--  WHERE gia_tri IS NULL OR gia_tri NOT BETWEEN 0 AND 20;
-- SELECT ma_can, "Diện tích", dien_tich_so FROM salemate_v1 WHERE dien_tich_so IS NULL;

-- ------------------------------------------------------------
-- 4) Index cho bộ lọc tìm kiếm
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_salemate_tinh_trang ON salemate_v1 ("Tình trạng (Còn/Hết)");
CREATE INDEX IF NOT EXISTS idx_salemate_gia_tri    ON salemate_v1 (gia_tri);
CREATE INDEX IF NOT EXISTS idx_salemate_toa        ON salemate_v1 ("Tòa");

-- ------------------------------------------------------------
-- 5) Chạy xong file này thì CHẠY LẠI 002 để gắn hai khoá ngoại về
--    salemate_v1(ma_can), rồi KHỞI ĐỘNG LẠI backend để bật bộ lọc giá.
-- ------------------------------------------------------------
