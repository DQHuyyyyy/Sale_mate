-- ============================================================
-- 010 — Ba trạng thái căn: Còn / Đã đặt cọc / Đã bán
--
-- VẤN ĐỀ: `dat_coc_lead` (009) ghi lead xong thì KHÔNG có gì đổi. Đo ngày
-- 19/08/2026: hai lead thật (VOP397 ngày 17/08, VOP908 ngày 18/08) đều
-- trang_thai='new', mà cả hai căn vẫn hiện "Còn" ở cả portal lẫn chatbot. Trợ
-- lý tiếp tục chào hai căn đó cho khách mới như chưa có ai hỏi.
--
-- Trạng thái cũ chỉ có hai mức vì view ép nhị phân:
--     CASE WHEN "Tình trạng (Còn/Hết)" = 'Còn' THEN 'available' ELSE 'sold' END
-- Mọi thứ khác 'Còn' thành 'sold', nên không có chỗ cho "đang có người giữ".
--
-- ============================================================
-- VÌ SAO SUY RA TRONG VIEW, KHÔNG THÊM CỘT TRẠNG THÁI THỨ HAI
-- ============================================================
-- Ghi trạng thái vào `salemate_v1` nghĩa là có HAI nơi cùng nắm sự thật về một
-- căn: cột tình trạng và bảng lead. Dự án đã trả giá đúng một lần cho kiểu đó —
-- xem 005: bảng `inventory_units` sao chép từ `salemate_v1` rồi trôi dần, và
-- lúc phát hiện thì đã có 4 căn SAI GIÁ, cặp bị hoán đổi, không báo lỗi gì.
--
-- LEFT JOIN thì lệch dữ liệu trở thành chuyện không thể xảy ra: portal và
-- chatbot đọc cùng một view, và trạng thái đổi ngay khi lead đổi. Chatbot vẫn
-- chỉ được ghi vào `dat_coc_lead`, không đụng bảng tồn kho gốc.
--
-- ============================================================
-- ⚠️ TUYỆT ĐỐI KHÔNG KÉO CỘT NÀO CỦA LEAD RA VIEW
-- ============================================================
-- `inventory_units` được chatbot đọc, và TỪNG DÒNG của nó đi thẳng vào prompt
-- gửi cho OpenAI/Anthropic. `ho_ten` và `so_dien_thoai` lọt ra đây là chảy vào
-- log của nhà cung cấp LLM — bảng lead có RLS, log của họ thì không.
--
-- Nên subquery dưới đây chỉ gom hai giá trị BOOLEAN "có ai đang giữ không",
-- không select một cột thông tin cá nhân nào. Ai cần xem lead thì đọc thẳng
-- `dat_coc_lead` qua service role.
--
-- ============================================================
-- ÁNH XẠ VÒNG ĐỜI LEAD → TRẠNG THÁI CĂN
-- ============================================================
--   new, da_goi, da_coc  → 'reserved'  Đã đặt cọc
--   bo                   → không giữ căn, căn về "Còn"
--
-- Cột `trang_thai` của bảng lead vẫn giữ đủ bốn giá trị: mức độ chín của lead
-- (mới / đã gọi / đã nhận cọc) là việc NỘI BỘ của đội sale, đọc thẳng ở bảng
-- lead. Với người mua thì cả ba đều là một điều duy nhất — "căn này có người
-- rồi" — nên không đáng thành một trạng thái căn riêng.
--
-- Thứ tự ưu tiên: sold > reserved > available. Căn đã bán thì không lead nào
-- kéo ngược lại được — bán là trạng thái cuối.
--
-- KHÔNG CÓ HẠN TỰ HẾT: giữ chỗ chỉ nhả khi sale đổi lead sang 'bo'. Đây là
-- quyết định sản phẩm, và nó có cái giá của nó — lead bỏ dở sẽ khoá căn vô hạn.
-- Van xả duy nhất là màn hình quản trị; thiếu nó thì cách duy nhất trả căn về
-- "Còn" là chạy SQL tay trên production.
--
-- ============================================================
-- KIỂM TRA TRƯỚC (ghi lại số để đối chiếu ở cuối file)
--   SELECT status, count(*) FROM inventory_units GROUP BY 1;
--     -- kỳ vọng: available 97, sold 3
--   SELECT trang_thai, count(*) FROM dat_coc_lead GROUP BY 1;
--     -- kỳ vọng: new 2
-- ============================================================

-- Sale lọc lead theo trạng thái ở màn hình quản trị, và view join theo ma_can.
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_trang_thai ON dat_coc_lead (trang_thai);

-- Dựng lại view. Danh sách cột giữ NGUYÊN tên, kiểu và THỨ TỰ — CREATE OR
-- REPLACE VIEW chỉ chấp nhận đổi biểu thức, không chấp nhận đổi hình dạng cột.
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
            WHERE trang_thai <> 'bo'
            GROUP BY ma_can
        ) l ON l.ma_can = s.ma_can
    $view$, col_loai_can);
END
$migration$;

-- ============================================================
-- KIỂM TRA SAU
--
--   a) Hai căn có lead phải đổi trạng thái — kỳ vọng đúng 2 dòng 'reserved':
--      SELECT unit_code, status FROM inventory_units WHERE status = 'reserved';
--
--   b) Tổng số căn không đổi — kỳ vọng 100:
--      SELECT count(*) FROM inventory_units;
--
--   c) JOIN không nhân dòng. Một căn có hai lead vẫn phải ra MỘT dòng.
--      Kỳ vọng 0 dòng:
--      SELECT unit_code FROM inventory_units GROUP BY unit_code HAVING count(*) > 1;
--
--   d) Căn đã bán không bị lead kéo ngược. Kỳ vọng 3 dòng, tất cả 'sold':
--      SELECT unit_code, status FROM inventory_units
--      WHERE unit_code IN (SELECT ma_can FROM salemate_v1
--                          WHERE "Tình trạng (Còn/Hết)" IS DISTINCT FROM 'Còn');
--
--   e) View KHÔNG phơi thông tin cá nhân. Kỳ vọng 0 dòng:
--      SELECT column_name FROM information_schema.columns
--      WHERE table_name = 'inventory_units'
--        AND column_name IN ('ho_ten', 'so_dien_thoai', 'ghi_chu', 'session_id');
-- ============================================================
