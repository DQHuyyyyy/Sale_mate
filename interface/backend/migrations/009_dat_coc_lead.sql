-- ============================================================
-- 009 — Lead đặt cọc: nơi trợ lý ghi lại khách muốn giữ chỗ một căn
--
-- Đây là đích cuối của cả luồng tư vấn: khách xem căn, so sánh, tính khoản vay,
-- rồi để lại tên và số điện thoại để đội sale gọi chốt cọc. Trước file này,
-- toàn bộ hệ thống KHÔNG có chỗ nào giữ thông tin đó — trợ lý tư vấn xong là
-- khách đi mất, không ai biết họ là ai.
--
-- ⚠️ BẢNG NÀY CHỨA THÔNG TIN CÁ NHÂN CỦA KHÁCH THẬT (tên, số điện thoại).
-- Ba hệ quả phải nhớ:
--   1. Migration ở dự án này chạy THẲNG lên Supabase production. Chạy file này
--      là tạo bảng thật, và dữ liệu ghi vào là dữ liệu thật.
--   2. RLS bật mặc định, chỉ service role đọc được — xem 005_rls_policies.sql.
--      Không mở SELECT cho anon, nếu không số điện thoại khách nằm phơi trên
--      internet cho bất kỳ ai gọi API.
--   3. Đừng log nội dung bảng này. `trace()` ghi log theo session, và số điện
--      thoại lọt vào log là lọt ra ngoài phạm vi bảng có RLS.
--
-- VÌ SAO KHÔNG DÙNG BẢNG sales:
-- `sales` ghi giao dịch ĐÃ chốt, gắn với một sale_id có tài khoản. Lead thì
-- ngược lại: khách chưa có ai phụ trách, chưa có gì chốt, và người tạo ra bản
-- ghi là con bot. Nhét chung sẽ làm "doanh số" của đội sale phồng lên bằng
-- những cuộc gọi chưa ai nhấc máy.
--
-- VÌ SAO KHÔNG CÓ KHOÁ NGOẠI SANG salemate_v1:
-- Cùng lý do 002 phải hoãn hai khoá ngoại của nó — khoá chính trên ma_can do
-- 001 tạo và có thể chưa chạy. Mất một lead vì ràng buộc khoá còn tệ hơn một
-- mã căn mồ côi: lead là khách hàng thật đang chờ được gọi lại.
-- ============================================================

CREATE TABLE IF NOT EXISTS dat_coc_lead (
    id            SERIAL PRIMARY KEY,
    ma_can        VARCHAR(20)  NOT NULL,
    ho_ten        VARCHAR(100) NOT NULL DEFAULT '',
    so_dien_thoai VARCHAR(20)  NOT NULL,
    ghi_chu       TEXT         NOT NULL DEFAULT '',
    -- Phiên chat sinh ra lead. Cần khi đội sale muốn xem lại khách đã hỏi gì
    -- trước lúc để số — lọc log theo session_id là ra cả đường đi.
    session_id    VARCHAR(64)  NOT NULL DEFAULT '',
    -- new -> đã gọi -> đã cọc / bỏ. Để sale đánh dấu, trợ lý chỉ tạo bản ghi.
    trang_thai    VARCHAR(20)  NOT NULL DEFAULT 'new'
                  CHECK (trang_thai IN ('new', 'da_goi', 'da_coc', 'bo')),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Sale mở danh sách là muốn xem lead mới nhất trước, và lọc theo căn đang bán.
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_created ON dat_coc_lead (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dat_coc_lead_ma_can ON dat_coc_lead (ma_can);

-- Cùng một số gọi cọc cùng một căn hai lần trong ngày là bấm nhầm, không phải
-- hai khách. Chặn ở tầng DB vì trợ lý có thể chạy lại tool khi người dùng gõ
-- lại câu cũ. Không chặn theo tháng: khách đổi ý rồi quay lại là chuyện thật.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dat_coc_lead_khong_trung
    ON dat_coc_lead (ma_can, so_dien_thoai, (created_at::date));

ALTER TABLE dat_coc_lead ENABLE ROW LEVEL SECURITY;
