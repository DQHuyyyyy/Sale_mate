-- ============================================================
-- 000 — Bảng ảnh căn hộ
--
-- ĐÁNH SỐ 000 VÌ PHẢI CHẠY TRƯỚC 002: file 002_create_tables.sql tạo index và
-- khoá ngoại TRÊN bảng apartment_images mà không tự tạo bảng. Cài mới từ đầu
-- theo thứ tự 001 → 002 sẽ vỡ ở dòng `CREATE INDEX ... ON apartment_images`
-- nếu bảng chưa tồn tại. File này lấp chỗ đó.
--
-- Thứ tự đúng:  001 (khoá chính salemate_v1) → 000 (bảng ảnh) → 002 → 003 → …
-- Nghe ngược đời, nhưng đổi số của 001–004 sẽ làm lệch tài liệu và migration
-- đã chạy trên DB thật. Số 000 là cách ít gây xáo trộn nhất.
--
-- Chạy lại nhiều lần vẫn an toàn.
--
-- Bối cảnh: cột `Ảnh` trong salemate_v1 chứa TÊN FOLDER trên Google Drive
-- ("1. R103"), không phải link ảnh. Bảng này giữ link thật.
--
--     salemate_v1."Ảnh"  →  tên folder Drive  →  apartment_images.image_url
-- ============================================================


-- ------------------------------------------------------------
-- salemate_v1.ma_can phải duy nhất
-- ------------------------------------------------------------
-- Cần cho hai việc: làm khoá ngoại, và để PostgREST tự lồng ảnh vào kết quả
-- khi frontend gọi ?select=*,apartment_images(...).
-- Đã kiểm chứng trên dữ liệu thật: 100/100 ma_can duy nhất.
-- File 001 cũng thêm ràng buộc này; ở đây kiểm tra theo LOẠI ràng buộc nên
-- chạy file nào trước cũng được.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.salemate_v1'::regclass
          AND contype IN ('p', 'u')
          AND conkey = ARRAY[
              (SELECT attnum FROM pg_attribute
               WHERE attrelid = 'public.salemate_v1'::regclass AND attname = 'ma_can')
          ]
    ) THEN
        ALTER TABLE public.salemate_v1
            ADD CONSTRAINT uq_salemate_v1_ma_can UNIQUE (ma_can);
    END IF;
END $$;


-- ------------------------------------------------------------
-- Bảng ảnh
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.apartment_images (
    id            BIGSERIAL PRIMARY KEY,

    ma_can        TEXT        NOT NULL
                  REFERENCES public.salemate_v1 (ma_can) ON DELETE CASCADE,

    -- URL hiển thị. Hiện trỏ tới Google Drive; đổi sang Supabase Storage sau
    -- này chỉ cần cập nhật cột này, frontend không phải sửa dòng nào.
    image_url     TEXT        NOT NULL,

    -- ID gốc trên Drive. Giữ vì hai lý do: làm khoá chống trùng khi chạy lại
    -- script nạp ảnh, và để biết tải file nào nếu đổi nơi lưu.
    drive_file_id TEXT,
    file_name     TEXT,

    -- Điền khi đã chuyển ảnh sang Supabase Storage
    storage_path  TEXT,

    -- 0 = ảnh đại diện
    sort_order    INTEGER     NOT NULL DEFAULT 0,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bảng đã tồn tại từ trước mà thiếu cột thì bổ sung
ALTER TABLE public.apartment_images ADD COLUMN IF NOT EXISTS drive_file_id TEXT;
ALTER TABLE public.apartment_images ADD COLUMN IF NOT EXISTS file_name     TEXT;
ALTER TABLE public.apartment_images ADD COLUMN IF NOT EXISTS storage_path  TEXT;

-- Chạy lại script nạp ảnh không được nhân đôi bản ghi. Dùng drive_file_id làm
-- khoá chứ không dùng image_url, vì URL đổi được (đổi kích thước ảnh, hoặc
-- chuyển sang Supabase Storage).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_apartment_images_drive'
    ) THEN
        ALTER TABLE public.apartment_images
            ADD CONSTRAINT uq_apartment_images_drive UNIQUE (ma_can, drive_file_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_apartment_images_ma_can
    ON public.apartment_images (ma_can, sort_order);

COMMENT ON TABLE  public.apartment_images IS
    'Ảnh căn hộ. Nguồn hiện tại là link Google Drive công khai.';
COMMENT ON COLUMN public.apartment_images.drive_file_id IS
    'ID file trên Drive — khoá chống trùng, và để tải lại nếu đổi nơi lưu.';
COMMENT ON COLUMN public.apartment_images.image_url IS
    'URL hiển thị. Đổi nguồn ảnh không ảnh hưởng frontend.';
COMMENT ON COLUMN public.apartment_images.sort_order IS
    'Thứ tự hiển thị. 0 = ảnh đại diện.';

NOTIFY pgrst, 'reload schema';
