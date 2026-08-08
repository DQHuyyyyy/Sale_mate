-- ============================================================
-- 005 — Quyền đọc cho frontend (Row Level Security)
--
-- Chạy sau 000–004. Chạy lại nhiều lần vẫn an toàn.
--
-- Vấn đề đã gặp thật: Supabase bật RLS mặc định cho bảng tạo qua giao diện.
-- RLS bật mà không có policy nào thì `anon` đọc ra 0 dòng — KHÔNG báo lỗi, chỉ
-- rỗng. Đó là kiểu lỗi tốn nhiều giờ nhất vì trông như "API chạy nhưng không
-- có data".
-- ============================================================


-- ------------------------------------------------------------
-- Cho ĐỌC, không cho GHI
-- ------------------------------------------------------------
-- Tin đăng và ảnh là dữ liệu công khai của portal nên mở quyền đọc bằng
-- anon key. Ghi vẫn phải qua service_role (backend hoặc script) — anon không
-- sửa được dù có lấy được key từ mã nguồn trình duyệt.

ALTER TABLE public.salemate_v1 ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'salemate_v1'
          AND policyname = 'anon_read_units'
    ) THEN
        CREATE POLICY anon_read_units ON public.salemate_v1
            FOR SELECT USING (true);
    END IF;
END $$;


ALTER TABLE public.apartment_images ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'apartment_images'
          AND policyname = 'anon_read_images'
    ) THEN
        CREATE POLICY anon_read_images ON public.apartment_images
            FOR SELECT USING (true);
    END IF;
END $$;


-- Bắt PostgREST nạp lại schema — không có dòng này thì API có thể vẫn báo
-- "Could not find the table" trong vài phút sau khi đổi cấu trúc.
NOTIFY pgrst, 'reload schema';


-- ============================================================
-- Kiểm tra sau khi chạy
-- ============================================================
-- Xem policy đang có (kỳ vọng: mỗi bảng đúng MỘT policy SELECT, không có
-- policy nào cho INSERT/UPDATE/DELETE):
--
--   SELECT tablename, policyname, cmd FROM pg_policies
--   WHERE schemaname = 'public' ORDER BY tablename;
--
-- Số ảnh mỗi căn:
--   SELECT ma_can, count(*) FROM apartment_images GROUP BY ma_can ORDER BY 2 DESC;
--
-- Căn chưa có ảnh:
--   SELECT s.ma_can, s."Ảnh" FROM salemate_v1 s
--   LEFT JOIN apartment_images i ON i.ma_can = s.ma_can WHERE i.id IS NULL;
--
-- Đúng cách frontend gọi (PostgREST tự lồng ảnh vào):
--   /rest/v1/salemate_v1?select=*,apartment_images(image_url,sort_order)
