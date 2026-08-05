-- ============================================================
-- SalesMate — bảng ảnh căn hộ
-- Dán toàn bộ vào Supabase SQL Editor và chạy. An toàn khi chạy lại nhiều lần.
--
-- Bảng `salemate_v1` giữ nguyên, không đụng vào. Cột `Ảnh` trong đó chứa TÊN
-- FOLDER trên Google Drive ("1. R103"), không phải link. Bảng này giữ link thật.
--
--     salemate_v1."Ảnh"  →  tên folder Drive  →  apartment_images.image_url
-- ============================================================


-- ------------------------------------------------------------
-- Bước 1: salemate_v1.ma_can phải là khoá duy nhất
-- ------------------------------------------------------------
-- Cần cho hai việc: làm khoá ngoại, và để PostgREST tự lồng ảnh vào kết quả
-- khi frontend gọi ?select=*,apartment_images(...).
-- Đã kiểm chứng trên dữ liệu thật: 100/100 ma_can duy nhất.

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.salemate_v1'::regclass
          and contype in ('p', 'u')
          and conkey = array[
              (select attnum from pg_attribute
               where attrelid = 'public.salemate_v1'::regclass and attname = 'ma_can')
          ]
    ) then
        alter table public.salemate_v1
            add constraint uq_salemate_v1_ma_can unique (ma_can);
    end if;
end $$;


-- ------------------------------------------------------------
-- Bước 2: bảng ảnh
-- ------------------------------------------------------------

create table if not exists public.apartment_images (
    id            bigserial primary key,

    ma_can        text        not null
                  references public.salemate_v1 (ma_can) on delete cascade,

    -- URL hiển thị. Hiện trỏ tới Drive; sau này đổi sang Supabase Storage thì
    -- chỉ cập nhật cột này, frontend không phải sửa một dòng nào.
    image_url     text        not null,

    -- ID gốc trên Drive. Giữ lại vì hai lý do:
    --   · làm khoá chống trùng khi chạy lại script nạp ảnh
    --   · sau này muốn tải file về Supabase Storage thì biết tải cái nào
    drive_file_id text,

    file_name     text,

    -- Điền khi đã chuyển ảnh sang Supabase Storage
    storage_path  text,

    -- 0 = ảnh đại diện
    sort_order    integer     not null default 0,

    created_at    timestamptz not null default now()
);

-- Nếu bảng đã tồn tại từ trước mà thiếu cột thì bổ sung
alter table public.apartment_images add column if not exists drive_file_id text;
alter table public.apartment_images add column if not exists file_name     text;
alter table public.apartment_images add column if not exists storage_path  text;

-- Chạy lại script nạp ảnh không được nhân đôi bản ghi.
-- Dùng drive_file_id làm khoá chứ không dùng image_url, vì URL đổi được
-- (đổi kích thước ảnh, hoặc chuyển sang Supabase Storage).
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'uq_apartment_images_drive'
    ) then
        alter table public.apartment_images
            add constraint uq_apartment_images_drive unique (ma_can, drive_file_id);
    end if;
end $$;

create index if not exists idx_apartment_images_ma_can
    on public.apartment_images (ma_can, sort_order);

comment on table  public.apartment_images is
    'Ảnh căn hộ. Nguồn hiện tại là link Google Drive công khai.';
comment on column public.apartment_images.drive_file_id is
    'ID file trên Drive — khoá chống trùng, và để tải lại nếu đổi nơi lưu.';
comment on column public.apartment_images.image_url is
    'URL hiển thị. Đổi nguồn ảnh không ảnh hưởng frontend.';
comment on column public.apartment_images.sort_order is
    'Thứ tự hiển thị. 0 = ảnh đại diện.';


-- ------------------------------------------------------------
-- Bước 3: cho frontend đọc bằng anon key
-- ------------------------------------------------------------
-- Ảnh tin đăng là dữ liệu công khai nên chỉ mở quyền ĐỌC.
-- Ghi vẫn phải qua service_role (script nạp ảnh hoặc backend).

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


-- ------------------------------------------------------------
-- Bước 4: nạp lại schema cache của PostgREST
-- ------------------------------------------------------------
-- Không có dòng này thì API có thể vẫn báo "Could not find the table"
-- trong vài phút sau khi tạo bảng.

notify pgrst, 'reload schema';


-- ============================================================
-- Câu lệnh kiểm tra sau khi nạp ảnh
-- ============================================================
-- Số ảnh mỗi căn:
--   select ma_can, count(*) from apartment_images group by ma_can order by 2 desc;
--
-- Căn chưa có ảnh:
--   select s.ma_can, s."Ảnh"
--   from salemate_v1 s
--   left join apartment_images i on i.ma_can = s.ma_can
--   where i.id is null;
--
-- Đúng cách frontend gọi:
--   /rest/v1/salemate_v1?select=*,apartment_images(image_url,sort_order)
