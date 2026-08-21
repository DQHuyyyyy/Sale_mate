-- ============================================================
-- 012 — Vá schema `dat_coc_lead` cho khớp migration 009
--
-- 🔴 CHẠY FILE NÀY TRƯỚC MỌI FILE KHÁC ĐANG CHỜ. Nó vá một LỖ HỔNG DỮ LIỆU
--    đang mở trên production, không phải một cải tiến.
--
-- ============================================================
-- CHUYỆN GÌ ĐÃ XẢY RA
-- ============================================================
-- Bảng `dat_coc_lead` trên database KHÔNG do 009 tạo ra. Nó do
-- `DatCocDB.ensure_table()` của lõi AI tạo — hàm đó gọi
-- `metadata.create_all()` ở đầu mọi thao tác, nên lần đầu trợ lý ghi lead là
-- bảng ra đời, trước khi ai kịp chạy 009. Sau đó `CREATE TABLE IF NOT EXISTS`
-- của 009 thấy bảng đã có và bỏ qua im lặng.
--
-- Bảng SQLAlchemy dựng ra thiếu MỌI thứ 009 khai. Đo ngày 19/08/2026:
--
--   | 009 khai                          | Thực tế trên DB |
--   |-----------------------------------|-----------------|
--   | trang_thai ... DEFAULT 'new'      | không có default|
--   | CHECK (trang_thai IN (...))       | không có        |
--   | UNIQUE (ma_can, sdt, ngày)        | không có        |
--   | ENABLE ROW LEVEL SECURITY         | RLS = OFF       |
--
-- Lý do: `default="new"` của SQLAlchemy là mặc định phía PYTHON, không sinh ra
-- `DEFAULT` trong DDL; còn CHECK/UNIQUE/RLS thì SQLAlchemy không biết tới.
--
-- ============================================================
-- 🔴 HẬU QUẢ NGHIÊM TRỌNG NHẤT: RLS TẮT + anon CÓ TOÀN QUYỀN
-- ============================================================
-- Đo được:
--   anon -> DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE
--   pg_class.relrowsecurity = false
--
-- `anon` là role mà SUPABASE_ANON_KEY dùng, và khoá đó nằm trong frontend nên
-- coi như công khai. Nghĩa là bất kỳ ai có khoá anon đều ĐỌC được họ tên và số
-- điện thoại của mọi khách đã để lại thông tin, qua PostgREST, không cần đăng
-- nhập — và xoá hoặc sửa được luôn.
--
-- 009 đã lường trước đúng chuyện này ("số điện thoại khách nằm phơi trên
-- internet cho bất kỳ ai gọi API") nhưng dòng lệnh đó chưa bao giờ chạy.
--
-- Ứng dụng KHÔNG bị ảnh hưởng khi vá: cả lõi AI lẫn API sản phẩm đều nối bằng
-- DATABASE_URL với user `postgres`, tức chủ bảng, và chủ bảng bỏ qua RLS.
--
-- ============================================================
-- KIỂM TRA TRƯỚC
--   SELECT relrowsecurity FROM pg_class WHERE relname = 'dat_coc_lead';
--     -- kỳ vọng: f  (đó là lý do có file này)
--   SELECT trang_thai, count(*) FROM dat_coc_lead GROUP BY 1;
--     -- ghi lại để đối chiếu; mọi giá trị phải nằm trong 4 giá trị hợp lệ
-- ============================================================

-- 1. KHOÁ LẠI TRƯỚC. Đây là phần khẩn cấp, làm đầu tiên.
REVOKE ALL ON dat_coc_lead FROM anon;
REVOKE ALL ON dat_coc_lead FROM authenticated;
ALTER TABLE dat_coc_lead ENABLE ROW LEVEL SECURITY;

-- Không tạo policy nào: RLS bật mà không có policy nghĩa là chặn hết, và đó
-- đúng ý — chỉ service role (bypass RLS) mới được đọc bảng này.

-- 2. Mặc định cho hai cột mà INSERT bằng SQL thuần hay bỏ qua.
ALTER TABLE dat_coc_lead ALTER COLUMN trang_thai SET DEFAULT 'new';
ALTER TABLE dat_coc_lead ALTER COLUMN created_at SET DEFAULT now();

-- 3. Ràng buộc giá trị. Migration 010 suy trạng thái CĂN từ đúng cột này, nên
--    một giá trị lạ ở đây làm căn rơi về "Còn" mà không ai biết vì sao.
--    Dọn dữ liệu lạc trước, nếu không ALTER sẽ hỏng.
UPDATE dat_coc_lead SET trang_thai = 'new'
WHERE trang_thai IS NULL OR trang_thai NOT IN ('new', 'da_goi', 'da_coc', 'bo');

ALTER TABLE dat_coc_lead DROP CONSTRAINT IF EXISTS dat_coc_lead_trang_thai_check;
ALTER TABLE dat_coc_lead ADD CONSTRAINT dat_coc_lead_trang_thai_check
    CHECK (trang_thai IN ('new', 'da_goi', 'da_coc', 'bo'));

-- 4. Index mà 009 khai. Cái unique là chốt chặn "khách bấm nút hai lần".
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_created ON dat_coc_lead (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_ma_can ON dat_coc_lead (ma_can);
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_trang_thai ON dat_coc_lead (trang_thai);
-- ⚠️ `created_at::date` KHÔNG dùng được trong index: ép timestamptz sang date
-- phụ thuộc TimeZone của phiên nên Postgres đánh dấu STABLE, và index chỉ nhận
-- biểu thức IMMUTABLE. 009 viết đúng câu đó, nên nếu ai từng chạy 009 thì nó đã
-- nổ ngay tại dòng này — thêm một bằng chứng bảng hiện tại không do 009 tạo.
--
-- Chốt múi giờ bằng chữ thì biểu thức thành IMMUTABLE. Dùng UTC cho khớp
-- `da_co_hom_nay()` phía lõi AI, vốn so bằng `datetime.now(UTC).date()`.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dat_coc_lead_khong_trung
    ON dat_coc_lead (ma_can, so_dien_thoai, ((created_at AT TIME ZONE 'UTC')::date));

-- 5. Ai tạo lead. NULL = khách tự đặt trên portal hoặc qua widget chat; có giá
--    trị = sale đăng nhập rồi đặt hộ khách đang ngồi trước mặt.
--
--    Không NOT NULL, và không khoá ngoại cứng: lead của khách vãng lai vốn
--    không có sale nào, còn xoá một tài khoản sale thì không được kéo theo lead
--    của họ — lead là khách hàng thật đang chờ được gọi lại.
ALTER TABLE dat_coc_lead ADD COLUMN IF NOT EXISTS sale_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_sale ON dat_coc_lead (sale_id);

-- ============================================================
-- KIỂM TRA SAU — cả bốn phải đúng
--
--   a) RLS đã bật. Kỳ vọng: t
--      SELECT relrowsecurity FROM pg_class WHERE relname = 'dat_coc_lead';
--
--   b) anon không còn quyền nào. Kỳ vọng: 0 dòng
--      SELECT grantee, privilege_type FROM information_schema.role_table_grants
--      WHERE table_name = 'dat_coc_lead' AND grantee IN ('anon', 'authenticated');
--
--   c) Có default cho hai cột. Kỳ vọng: 2 dòng, đều khác NULL
--      SELECT column_name, column_default FROM information_schema.columns
--      WHERE table_name = 'dat_coc_lead' AND column_name IN ('trang_thai', 'created_at');
--
--   d) Có cột sale_id. Kỳ vọng: 1 dòng
--      SELECT column_name FROM information_schema.columns
--      WHERE table_name = 'dat_coc_lead' AND column_name = 'sale_id';
--
--   e) Có CHECK và unique index. Kỳ vọng: 1 và 1
--      SELECT count(*) FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
--      WHERE rel.relname = 'dat_coc_lead' AND con.contype = 'c';
--      SELECT count(*) FROM pg_indexes
--      WHERE tablename = 'dat_coc_lead' AND indexname = 'idx_dat_coc_lead_khong_trung';
--
-- SAU KHI CHẠY: đổi SUPABASE_ANON_KEY nếu khoá cũ từng phát ra ngoài. Vá quyền
-- chặn truy cập từ giờ trở đi, không lấy lại được dữ liệu ai đó đã đọc.
-- ============================================================
