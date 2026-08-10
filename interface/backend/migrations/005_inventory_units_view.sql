-- ============================================================
-- 005 — Thay bảng inventory_units bằng VIEW đọc thẳng salemate_v1
--
-- VÌ SAO: inventory_units trước đây là bảng RIÊNG, nạp một lần bằng
-- scripts/migrate_inventory.py. Không có gì đồng bộ nó với salemate_v1, nên nó
-- trôi dần khỏi sự thật. Đo được ngày 10/08/2026:
--
--   * VOP397 có trong salemate_v1 nhưng KHÔNG có trong inventory_units
--     (đổi mã căn sau khi ảnh chụp được tạo) -> chatbot không tra được căn này
--   * VOP399 thừa trong inventory_units, không còn trong salemate_v1
--   * 4 căn SAI GIÁ, các cặp bị hoán đổi -- lệch dòng lúc migrate:
--       VOP872 thật 4,05 tỷ  -> bảng ghi 3,55 tỷ
--       VOP873 thật 3,55 tỷ  -> bảng ghi 4,05 tỷ
--       VOP954 thật 3,15 tỷ  -> bảng ghi "3.55"
--       VOP955 thật 3,55 tỷ  -> bảng ghi 3,15 tỷ
--
-- Sai giá là kiểu hỏng tệ nhất: không báo lỗi, trợ lý đọc số sai cho khách.
--
-- SAU FILE NÀY: một nguồn sự thật duy nhất là salemate_v1. Lệch dữ liệu trở
-- thành chuyện không thể xảy ra, không phải chuyện phải nhớ đồng bộ.
--
-- Code KHÔNG phải sửa gì: tool vẫn SELECT ... FROM inventory_units như cũ.
-- SQLAlchemy metadata.create_all(checkfirst=True) thấy has_table() = True với
-- view nên bỏ qua bước tạo bảng.
--
-- ĐÁNH ĐỔI: view chỉ đọc. interface/backend/scripts/migrate_inventory.py sẽ
-- không chạy được nữa -- đúng ý, vì chính nó tạo ra bản sao lệch này.
--
-- VÌ SAO PHẢI DÙNG DO/EXECUTE THAY VÌ CREATE VIEW THẲNG:
-- Cột loại căn tên là 'Loại căn\n(PN, WC) Studio' -- có ký tự XUỐNG DÒNG thật
-- nằm giữa "căn" và "(PN". Gõ tên đó vào SQL nghĩa là gõ một dấu xuống dòng
-- bên trong dấu nháy kép, mà file trên Windows dùng CRLF nên dán vào editor sẽ
-- thành \r\n -- KHÁC với \n của tên cột thật, và Postgres báo
-- 'column does not exist'. Ở đây tra tên cột từ information_schema rồi ghép
-- bằng format(%I), nên không phụ thuộc kiểu xuống dòng của file lẫn editor.
-- ============================================================

-- 1. KIỂM TRA TRƯỚC -- chạy riêng, ghi lại số để đối chiếu ở bước 4.
--    SELECT count(*) FROM salemate_v1;        -- kỳ vọng 100
--    SELECT count(*) FROM inventory_units;    -- kỳ vọng 100 (bảng cũ)

-- 2. Bỏ bảng cũ. Dữ liệu trong đó là bản sao lệch, không mất gì --
--    salemate_v1 giữ toàn bộ sự thật.
DROP TABLE IF EXISTS inventory_units;

-- 3. Dựng view. Tên và kiểu cột giữ NGUYÊN như bảng cũ để tool không phải sửa.
DO $migration$
DECLARE
    col_loai_can text;
BEGIN
    -- INTO STRICT: không tìm thấy hoặc thấy nhiều hơn một cột thì dừng ngay và
    -- báo lỗi, thay vì lặng lẽ dựng view thiếu cột.
    SELECT column_name INTO STRICT col_loai_can
    FROM information_schema.columns
    WHERE table_name = 'salemate_v1'
      AND column_name LIKE 'Lo%i c%n%';

    EXECUTE format($view$
        CREATE VIEW inventory_units AS
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
            END                              AS photos
        FROM salemate_v1
    $view$, col_loai_can);
END
$migration$;

-- Ghi chú về cột status: 'Còn' là giá trị duy nhất nghĩa là còn bán. Mọi giá
-- trị khác, kể cả NULL, coi như đã bán -- để không bao giờ chào khách một căn
-- không còn hàng.

-- 4. KIỂM TRA SAU -- cả ba câu phải trả về 0 dòng.

--    a) Không còn mã nào lệch giữa hai bên:
--    SELECT s.ma_can FROM salemate_v1 s
--    WHERE NOT EXISTS (SELECT 1 FROM inventory_units i WHERE i.unit_code = s.ma_can);

--    b) Không còn căn nào lệch giá:
--    SELECT s.ma_can, s."Giá", i.price_label
--    FROM salemate_v1 s JOIN inventory_units i ON i.unit_code = s.ma_can
--    WHERE s."Giá" IS DISTINCT FROM i.price_label;

--    c) VOP397 giờ phải tra được -- kỳ vọng 1 dòng, không phải 0:
--    SELECT unit_code, price_label, status FROM inventory_units WHERE unit_code = 'VOP397';
