-- ============================================================
-- 013 — Trạng thái lead `da_ban`: chốt bán ngay từ màn Giao dịch
--
-- VÌ SAO: lead đi hết đường `new → da_goi → da_coc` rồi dừng. Muốn ghi nhận đã
-- bán thì sale phải bỏ màn Giao dịch, mở trang căn hộ, bấm "Ghi nhận đã bán" và
-- GÕ LẠI tên với số điện thoại của chính khách đang nằm trong lead. Vừa thừa
-- việc vừa dễ gõ sai — và gõ sai thì `sales_history` mang một khách khác với
-- người thật sự mua.
--
-- Sau file này, bấm "Đã bán" trên một lead làm ba việc trong MỘT transaction:
--   1. INSERT sales_history, lấy tên + số điện thoại từ chính lead
--   2. UPDATE salemate_v1 "Tình trạng (Còn/Hết)" = 'Hết'
--   3. UPDATE lead trang_thai = 'da_ban'
--
-- Dòng lead KHÔNG biến mất — nó chuyển sang "Đã bán" và ở lại trong bảng. Đó là
-- lịch sử của một giao dịch có thật, xoá đi thì không ai truy được khách này
-- đến từ đâu.
--
-- ============================================================
-- KIỂM TRA TRƯỚC
--   SELECT trang_thai, count(*) FROM dat_coc_lead GROUP BY 1;
--   SELECT pg_get_constraintdef(oid) FROM pg_constraint
--   WHERE conname = 'dat_coc_lead_trang_thai_check';
--     -- kỳ vọng: CHECK (... IN ('new','da_goi','da_coc','bo'))  — chưa có da_ban
-- ============================================================

-- 1. Nới CHECK cho giá trị thứ năm.
ALTER TABLE dat_coc_lead DROP CONSTRAINT IF EXISTS dat_coc_lead_trang_thai_check;
ALTER TABLE dat_coc_lead ADD CONSTRAINT dat_coc_lead_trang_thai_check
    CHECK (trang_thai IN ('new', 'da_goi', 'da_coc', 'bo', 'da_ban'));

-- 2. Dựng lại view: lead `da_ban` KHÔNG còn giữ căn nữa.
--
-- Thực tế `sold` vẫn thắng theo thứ tự ưu tiên nên kết quả không đổi hôm nay.
-- Nhưng để lead đã bán nằm trong nhóm "đang giữ" là sai về nghĩa, và nó sẽ cắn
-- vào đúng lúc có người mở lại một căn đã bán — căn đó lập tức thành "Đã đặt
-- cọc" bởi một giao dịch đã đóng từ lâu.
--
-- Vẫn dùng DO/EXECUTE vì tên cột loại căn chứa ký tự xuống dòng thật; chú thích
-- đầy đủ ở 005.
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
            s.ma_can::varchar                  AS unit_code,
            s."Tòa"::varchar                   AS building,
            s."Tầng"::varchar                  AS floor,
            s."Số phòng"::varchar              AS room_no,
            s.%I::varchar                      AS unit_type,
            s."Diện tích"::varchar             AS area_m2,
            s."Hướng phong thủy"::varchar      AS direction,
            s."View"::varchar                  AS view,
            s."Số đỏ"::varchar                 AS legal_status,
            s."Giá"::varchar                   AS price_label,
            s."Nội thất"::varchar              AS furniture,
            CASE
                WHEN s."Tình trạng (Còn/Hết)" IS DISTINCT FROM 'Còn' THEN 'sold'
                WHEN coalesce(l.dang_giu, false) THEN 'reserved'
                ELSE 'available'
            END::varchar                       AS status,
            CASE
                WHEN s."Ảnh" IS NULL OR btrim(s."Ảnh") = '' THEN '[]'::json
                ELSE to_json(string_to_array(s."Ảnh", ','))
            END                                AS photos,
            s.gia_tri                          AS price_value,
            s.dien_tich_so                     AS area_value,
            s."Phân khu"::varchar              AS subdivision
        FROM salemate_v1 s
        LEFT JOIN (
            -- CHỈ một boolean. Không ho_ten, không so_dien_thoai, không ghi_chu.
            SELECT ma_can, true AS dang_giu
            FROM dat_coc_lead
            WHERE trang_thai NOT IN ('bo', 'da_ban')
            GROUP BY ma_can
        ) l ON l.ma_can = s.ma_can
    $view$, col_loai_can);
END
$migration$;

-- ============================================================
-- KIỂM TRA SAU
--
--   a) CHECK nhận đủ năm giá trị. Kỳ vọng: chuỗi có 'da_ban'
--      SELECT pg_get_constraintdef(oid) FROM pg_constraint
--      WHERE conname = 'dat_coc_lead_trang_thai_check';
--
--   b) Tổng số căn không đổi — kỳ vọng 100:
--      SELECT count(*) FROM inventory_units;
--
--   c) View vẫn không phơi thông tin cá nhân. Kỳ vọng 0 dòng:
--      SELECT column_name FROM information_schema.columns
--      WHERE table_name = 'inventory_units'
--        AND column_name IN ('ho_ten', 'so_dien_thoai', 'ghi_chu', 'session_id');
-- ============================================================
