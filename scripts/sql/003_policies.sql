-- ============================================================
-- SalesMate — quyền đọc cho frontend
-- Dán vào Supabase SQL Editor và chạy. An toàn khi chạy lại.
--
-- Vấn đề: Supabase bật RLS mặc định cho bảng tạo qua giao diện. RLS bật mà
-- không có policy nào thì `anon` đọc ra 0 dòng — không báo lỗi, chỉ rỗng.
-- Đó là kiểu lỗi tốn nhiều giờ nhất vì trông như "API chạy nhưng không có data".
-- ============================================================


-- ------------------------------------------------------------
-- Cho đọc, KHÔNG cho ghi
-- ------------------------------------------------------------
-- Tin đăng và ảnh là dữ liệu công khai của portal nên mở quyền đọc.
-- Ghi vẫn phải qua service_role (backend hoặc script) — anon không sửa được
-- dù có lấy được key từ mã nguồn trình duyệt.

alter table public.salemate_v1 enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'salemate_v1'
          and policyname = 'anon_read_units'
    ) then
        create policy anon_read_units on public.salemate_v1
            for select using (true);
    end if;
end $$;


-- apartment_images đã có policy từ file 002, thêm ở đây cho chắc
alter table public.apartment_images enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'apartment_images'
          and policyname = 'anon_read_images'
    ) then
        create policy anon_read_images on public.apartment_images
            for select using (true);
    end if;
end $$;


notify pgrst, 'reload schema';


-- ============================================================
-- Kiểm tra sau khi chạy
-- ============================================================
-- Xem policy đang có:
--   select tablename, policyname, cmd
--   from pg_policies
--   where schemaname = 'public'
--   order by tablename;
--
-- Kỳ vọng: mỗi bảng có đúng một policy SELECT.
-- KHÔNG được có policy nào cho INSERT / UPDATE / DELETE.
