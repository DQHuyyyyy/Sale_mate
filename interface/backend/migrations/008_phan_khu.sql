-- ============================================================
-- 008 — Phân khu: thêm cột vào salemate_v1, seed zones/towers, phơi ra view
--
-- ⚠️ DỮ LIỆU GIẢ. Dự án chưa có thông tin phân khu thật, file này sinh dữ liệu
-- DEMO để giao diện và trợ lý có cái mà chạy. Trợ lý sẽ nói con số này với
-- khách như sự thật — khi nào có dữ liệu thật thì chạy lại phần UPDATE với
-- bảng ánh xạ đúng, đừng để bản giả sống tiếp lên production thật.
--
-- VÌ SAO GÁN THEO TOÀ, KHÔNG PHẢI THEO TỪNG CĂN:
-- random() từng dòng sẽ đẩy 8 căn của toà S109 vào ba phân khu khác nhau. Một
-- toà nhà không thể nằm ở ba phân khu; ai nhìn dữ liệu cũng thấy sai ngay.
-- Gán theo toà thì bịa vẫn là bịa, nhưng ít nhất tự nhất quán.
--
-- VÌ SAO hashtext() CHỨ KHÔNG PHẢI random():
-- random() đổi kết quả mỗi lần chạy, nên chạy lại migration là xáo lại toàn bộ
-- phân khu — căn khách vừa xem hôm qua hôm nay đã sang khu khác. hashtext ổn
-- định theo tên toà: chạy bao nhiêu lần cũng ra đúng một kết quả.
--
-- VÌ SAO SEED CẢ zones/towers:
-- Dự án ĐÃ CÓ mô hình phân khu (bảng zones + towers, trang "Sơ đồ phân khu"),
-- chỉ là chưa ai đổ dữ liệu — cả hai bảng đang rỗng. Thêm một cột phân khu
-- riêng mà để hai bảng kia trống là tạo ra đúng thứ dự án này đã bị hai lần:
-- hai nguồn số liệu cho cùng một câu hỏi. Ở đây cả ba chỗ lấy từ MỘT phép gán.
-- ============================================================

-- 1. Cột phân khu trên bảng gốc.
ALTER TABLE salemate_v1 ADD COLUMN IF NOT EXISTS "Phân khu" varchar;

-- 2. Bảng ánh xạ toà -> phân khu, dùng chung cho cả ba bước sau.
--    abs(hashtext(...)) % 3 cho ra 0/1/2 ổn định theo tên toà.
CREATE TEMP VIEW _gan_phan_khu AS
SELECT DISTINCT
    "Tòa" AS toa,
    (ARRAY['Ocean Park 1', 'Ocean Park 2', 'Ocean Park 3'])[abs(hashtext("Tòa")) % 3 + 1] AS phan_khu
FROM salemate_v1
WHERE "Tòa" IS NOT NULL AND btrim("Tòa") <> '';

-- 3. Điền cột phân khu cho từng căn.
UPDATE salemate_v1 s
SET "Phân khu" = g.phan_khu
FROM _gan_phan_khu g
WHERE s."Tòa" = g.toa;

-- 4. Seed zones — 3 phân khu. ON CONFLICT không dùng được vì `code` chưa có
--    ràng buộc unique, nên chèn có điều kiện.
INSERT INTO zones (code, name, description)
SELECT v.code, v.name, v.mo_ta
FROM (VALUES
    ('OP1', 'Ocean Park 1', 'Phân khu đầu tiên của đại đô thị Vinhomes Ocean Park.'),
    ('OP2', 'Ocean Park 2', 'Phân khu thứ hai, quảng trường Kinh Đô Ánh Sáng.'),
    ('OP3', 'Ocean Park 3', 'Phân khu thứ ba, khu đô thị ven sông.')
) AS v(code, name, mo_ta)
WHERE NOT EXISTS (SELECT 1 FROM zones z WHERE z.code = v.code);

-- 5. Seed towers từ CHÍNH phép gán ở bước 2 — không gán lại lần nữa.
INSERT INTO towers (code, name, zone_id)
SELECT g.toa, 'Tòa ' || g.toa, z.id
FROM _gan_phan_khu g
JOIN zones z ON z.name = g.phan_khu
WHERE NOT EXISTS (SELECT 1 FROM towers t WHERE t.code = g.toa);

-- 6. Phơi phân khu ra view để tool tồn kho và chatbot đọc được.
--    Vẫn dùng DO/EXECUTE vì tên cột loại căn chứa ký tự xuống dòng thật; xem
--    chú thích đầy đủ ở 005.
DO $migration$
DECLARE
    col_loai_can text;
BEGIN
    SELECT column_name INTO STRICT col_loai_can
    FROM information_schema.columns
    WHERE table_name = 'salemate_v1' AND column_name LIKE 'Lo%i c%n%';

    EXECUTE format($view$
        CREATE OR REPLACE VIEW inventory_units AS
        SELECT
            ma_can::varchar                  AS unit_code,
            "Tòa"::varchar                   AS building,
            "Tầng"::varchar                  AS floor,
            "Số phòng"::varchar              AS room_no,
            %I::varchar                      AS unit_type,
            "Diện tích"::varchar             AS area_m2,
            "Hướng phong thủy"::varchar      AS direction,
            "View"::varchar                  AS view,
            "Số đỏ"::varchar                 AS legal_status,
            "Giá"::varchar                   AS price_label,
            "Nội thất"::varchar              AS furniture,
            CASE WHEN "Tình trạng (Còn/Hết)" = 'Còn'
                 THEN 'available' ELSE 'sold' END::varchar
                                             AS status,
            CASE
                WHEN "Ảnh" IS NULL OR btrim("Ảnh") = '' THEN '[]'::json
                ELSE to_json(string_to_array("Ảnh", ','))
            END                              AS photos,
            gia_tri                          AS price_value,
            dien_tich_so                     AS area_value,
            -- Cột MỚI, thêm vào cuối để CREATE OR REPLACE chấp nhận.
            "Phân khu"::varchar              AS subdivision
        FROM salemate_v1
    $view$, col_loai_can);
END
$migration$;

DROP VIEW _gan_phan_khu;

-- KIỂM TRA — chạy sau khi migration xong.

--    a) Không căn nào thiếu phân khu (kỳ vọng 0 dòng):
--    SELECT ma_can FROM salemate_v1 WHERE "Phân khu" IS NULL;

--    b) Mỗi toà CHỈ thuộc một phân khu (kỳ vọng 0 dòng):
--    SELECT "Tòa" FROM salemate_v1 GROUP BY "Tòa" HAVING count(DISTINCT "Phân khu") > 1;

--    c) Phân bố ba phân khu:
--    SELECT subdivision, count(*) FROM inventory_units GROUP BY 1 ORDER BY 1;

--    d) zones/towers khớp với cột trên bảng gốc (kỳ vọng 0 dòng):
--    SELECT s."Tòa", s."Phân khu", z.name
--    FROM salemate_v1 s JOIN towers t ON t.code = s."Tòa" JOIN zones z ON z.id = t.zone_id
--    WHERE z.name IS DISTINCT FROM s."Phân khu";
