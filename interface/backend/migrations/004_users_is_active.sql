-- ============================================================
-- 004 — Vô hiệu hoá tài khoản thay vì xoá hẳn
--
-- Xoá hẳn một sale đã từng bán căn sẽ vi phạm khoá ngoại
-- sales_history.sale_id, và nếu xoá được thì doanh số của người đó cũng biến
-- mất khỏi báo cáo "Căn đã bán toàn hệ thống". Nên tài khoản chỉ bị TẮT.
--
-- Chạy lại nhiều lần vẫn an toàn.
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Tài khoản tắt không đăng nhập được, và token đã phát cũng hết hiệu lực ngay
-- lần gọi API kế tiếp (get_current_user đọc lại cờ này từ DB mỗi request).
COMMENT ON COLUMN users.is_active IS
    'FALSE = tài khoản bị vô hiệu hoá: không đăng nhập được, token cũ mất hiệu lực. Lịch sử bán vẫn giữ nguyên.';

CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active);
