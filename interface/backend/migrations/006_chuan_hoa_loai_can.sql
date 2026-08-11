-- 006 — Chuẩn hoá cột loại căn: 10 cách viết -> 6 loại thật
--
-- Trước:  '1 PN, 1WC' x19 · '1PN, 1 WC' x1 · '1PN, 1WC' x21  (cùng một loại)
-- Sau:    '1PN, 1WC' x41
--
-- Vì sao cần: dropdown "Loại căn" trên portal hiện 10 lựa chọn thay vì 6, và
-- lọc '2PN, 1WC' chỉ ra 10 căn thay vì 14 — bỏ sót 4 căn ghi '2 PN, 1WC'.
--
-- Dùng DO/EXECUTE vì tên cột chứa ký tự xuống dòng thật, gõ thẳng vào SQL sẽ
-- hỏng khi file dùng CRLF. Xem chú thích đầy đủ ở 005.

DO $migration$
DECLARE
    col text;
BEGIN
    SELECT column_name INTO STRICT col
    FROM information_schema.columns
    WHERE table_name = 'salemate_v1' AND column_name LIKE 'Lo%i c%n%';

    -- Bỏ khoảng trắng thừa trước PN/WC, gộp nhiều dấu cách thành một.
    EXECUTE format(
        'UPDATE salemate_v1 SET %1$I = btrim(regexp_replace('
        'replace(replace(%1$I, '' PN'', ''PN''), '' WC'', ''WC''), ''\s+'', '' '', ''g''))',
        col
    );
END
$migration$;

-- KIỂM TRA — phải còn đúng 6 dòng, không còn biến thể nào chỉ khác dấu cách:
--    SELECT "Loại căn
-- (PN, WC) Studio", count(*) FROM salemate_v1 GROUP BY 1 ORDER BY 1;
--
-- Hoặc tránh gõ tên cột:
--    SELECT unit_type, count(*) FROM inventory_units GROUP BY 1 ORDER BY 1;
