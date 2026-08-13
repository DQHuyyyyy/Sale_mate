-- 007 — Thêm cột SỐ vào view inventory_units: price_value, area_value
--
-- VÌ SAO: view ở migration 005 chỉ phơi `price_label` dạng chữ ("2,25 tỷ",
-- "2,120 tỷ" — 65 định dạng khác nhau). Muốn lọc "căn dưới 3 tỷ" thì phải parse
-- chuỗi, vừa mong manh vừa sai lệch.
--
-- Trong khi `salemate_v1` ĐÃ CÓ SẴN hai cột số `gia_tri` và `dien_tich_so`
-- (GENERATED, Postgres tự tính từ cột chữ). Migration 005 chỉ quên đưa ra.
--
-- Sau file này, tool tồn kho lọc được theo khoảng giá và khoảng diện tích bằng
-- số thật, không đoán từ chuỗi.
--
-- CREATE OR REPLACE VIEW chỉ cho THÊM cột vào cuối và giữ nguyên tên/thứ tự cột
-- cũ — đúng thứ cần ở đây, nên không phải DROP rồi tạo lại.
--
-- Vẫn dùng DO/EXECUTE vì tên cột loại căn chứa ký tự xuống dòng thật; xem chú
-- thích đầy đủ ở 005.

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
            -- Hai cột MỚI, thêm vào cuối. Đơn vị: tỷ đồng và m2.
            gia_tri                          AS price_value,
            dien_tich_so                     AS area_value
        FROM salemate_v1
    $view$, col_loai_can);
END
$migration$;

-- KIỂM TRA — cả ba câu phải trả kết quả hợp lý.

--    a) Hai cột mới có mặt và có giá trị:
--    SELECT unit_code, price_label, price_value, area_m2, area_value
--    FROM inventory_units ORDER BY price_value LIMIT 5;

--    b) Không căn nào thiếu số (0 dòng là đạt):
--    SELECT unit_code FROM inventory_units
--    WHERE price_value IS NULL OR area_value IS NULL;

--    c) Câu hỏi đang hỏng phải ra số đúng — "còn hàng, dưới 3 tỷ":
--    SELECT count(*) FROM inventory_units
--    WHERE status = 'available' AND price_value < 3;
