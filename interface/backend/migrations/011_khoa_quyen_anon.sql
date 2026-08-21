-- ============================================================
-- 011 — 🔴 KHẨN: khoá quyền `anon` trên toàn bộ schema public
--
-- ĐÂY LÀ VÁ MỘT LỖ HỔNG ĐANG BỊ KHAI THÁC ĐƯỢC, KHÔNG PHẢI CẢI TIẾN.
-- Chạy file này TRƯỚC mọi migration khác đang chờ.
--
-- ============================================================
-- ĐÃ KIỂM CHỨNG (19/08/2026) — không phải suy đoán
-- ============================================================
-- Gọi thẳng PostgREST bằng đúng SUPABASE_ANON_KEY trong .env, không đăng nhập:
--
--   GET /rest/v1/users?select=*         -> 200, đọc được password_hash của admin
--   GET /rest/v1/dat_coc_lead?select=*  -> 200, đọc được họ tên + số điện thoại khách
--   GET /rest/v1/sales_history?select=* -> 200, đọc được tên + số điện thoại người mua
--
-- Khoá anon vốn được thiết kế để CÔNG KHAI (Supabase nhúng nó vào frontend),
-- nên coi như ai cũng có. Thứ đáng lẽ phải chặn là RLS — và RLS đang TẮT.
--
-- Tám bảng ở trạng thái "RLS off + anon toàn quyền":
--   chat_messages · dat_coc_lead · documents · inventory_units
--   sales_history · towers · users · zones
--
-- `anon` có cả INSERT/UPDATE/DELETE, không chỉ SELECT. Nguy hiểm nhất là
-- `users`: sửa được `role` hoặc ghi đè `password_hash` là chiếm được tài khoản
-- quản trị.
--
-- ============================================================
-- VÌ SAO XẢY RA
-- ============================================================
-- Supabase mặc định `GRANT ALL ON ALL TABLES IN SCHEMA public TO anon,
-- authenticated`, và trông cậy hoàn toàn vào RLS để chặn. Mô hình đó đúng —
-- nhưng chỉ khi mọi bảng đều bật RLS.
--
-- Bảng ở dự án này sinh ra bằng hai đường: migration (005_rls_policies có bật
-- RLS cho `salemate_v1`, `apartment_images`) và `metadata.create_all()` của
-- SQLAlchemy trong lõi AI (không biết RLS là gì). Đường thứ hai đẻ ra bảng mở.
--
-- ============================================================
-- VÌ SAO REVOKE HẲN, KHÔNG CHỈ BẬT RLS
-- ============================================================
-- **Không có gì trong dự án dùng PostgREST.** Đã kiểm:
--   - frontend không cài `@supabase/supabase-js`, không import supabase ở đâu
--   - `supabase_anon_key` chỉ được KHAI trong `src/core/config.py`, không nơi
--     nào đọc tới
--   - backend chỉ dùng `supabase_url` + service role key cho STORAGE (ảnh căn)
--   - mọi truy cập dữ liệu đi qua `DATABASE_URL` với user `postgres`
--
-- Một cửa không ai đi qua mà vẫn mở thì đóng hẳn, đừng chỉ khoá bằng RLS. Bật
-- RLS là lớp hai, phòng khi sau này có người mở lại quyền.
--
-- ỨNG DỤNG KHÔNG BỊ ẢNH HƯỞNG: cả hai service nối bằng user `postgres` (chủ
-- bảng), và chủ bảng bỏ qua RLS.
--
-- ============================================================
-- KIỂM TRA TRƯỚC — ghi lại để đối chiếu
--   SELECT c.relname, c.relrowsecurity FROM pg_class c
--   JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname = 'public' AND c.relkind IN ('r','v') ORDER BY 1;
-- ============================================================

-- 1. CẮT QUYỀN. Phần khẩn cấp, làm đầu tiên và làm cho tất cả.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE USAGE ON SCHEMA public FROM anon, authenticated;

-- 2. CHẶN TÁI DIỄN. Không có bước này thì bảng TẠO SAU sẽ lại được cấp quyền
--    y hệt — đúng cách tám bảng trên trở thành mở.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- 3. BẬT RLS cho mọi BẢNG chưa có. Lớp phòng thủ thứ hai, độc lập với quyền:
--    ai đó cấp lại quyền trong tương lai thì RLS vẫn chặn.
--    Không tạo policy nào — RLS bật mà không policy nghĩa là chặn hết, đúng ý.
DO $rls$
DECLARE
    ten text;
BEGIN
    FOR ten IN
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', ten);
        RAISE NOTICE 'Đã bật RLS cho %', ten;
    END LOOP;
END
$rls$;

-- 4. VIEW không bật RLS được, và mặc định nó chạy bằng quyền của CHỦ view nên
--    **đi vòng qua RLS của bảng gốc**. Đó là lý do `inventory_units` đọc được
--    dù `salemate_v1` đã bật RLS từ 005. `security_invoker` bắt view tôn trọng
--    quyền của người gọi. Cần PostgreSQL 15+; bản cũ hơn thì bỏ qua, vì bước 1
--    đã cắt quyền rồi.
DO $view$
BEGIN
    EXECUTE 'ALTER VIEW public.inventory_units SET (security_invoker = on)';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Không đặt được security_invoker (PostgreSQL < 15?): %', SQLERRM;
END
$view$;

-- ============================================================
-- KIỂM TRA SAU — cả ba phải đúng
--
--   a) Không bảng nào còn RLS tắt. Kỳ vọng: 0 dòng
--      SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--      WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity;
--
--   b) anon không còn quyền nào. Kỳ vọng: 0 dòng
--      SELECT table_name, grantee FROM information_schema.role_table_grants
--      WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');
--
--   c) Gọi lại bằng khoá anon phải bị chặn. Kỳ vọng: 401 hoặc 404, KHÔNG phải 200
--      curl -s -o /dev/null -w "%{http_code}\n" \
--        -H "apikey: $SUPABASE_ANON_KEY" \
--        "$SUPABASE_URL/rest/v1/users?select=id&limit=1"
--
-- CHƯA XONG SAU KHI CHẠY FILE NÀY — xem phần "việc phải làm tay" trong
-- báo cáo kèm theo:
--   * Dashboard → Settings → API → Exposed schemas: bỏ `public`
--   * Đổi mật khẩu MỌI tài khoản (password_hash đã nằm ngoài)
--   * Soát log Supabase xem đã có ai đọc chưa
-- ============================================================
