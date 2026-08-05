-- ============================================================
-- 003 — Seed dữ liệu nền: zones + towers
-- Chạy sau 002. Chạy lại nhiều lần vẫn an toàn (ON CONFLICT DO NOTHING).
--
-- Tài khoản đăng nhập KHÔNG seed ở đây vì mật khẩu phải hash.
-- Sinh SQL cho users bằng:  python backend/scripts/seed_users.py
-- ============================================================

-- Phân khu. Sửa lại tên/mô tả cho đúng dự án thật.
INSERT INTO zones (code, name, description) VALUES
    ('S', 'Phân khu Sapphire',
     'Các tòa S, gần công viên và quảng trường, mật độ thấp, view thoáng.'),
    ('R', 'Phân khu Ruby',
     'Các tòa R, view biệt thự và quảng trường BayFront, tiện ích nội khu đầy đủ.')
ON CONFLICT (code) DO NOTHING;

-- Tòa: lấy thẳng từ dữ liệu thật trong salemate_v1, gán khu theo chữ cái đầu
-- ('S1','S2' -> khu S; 'R1' -> khu R). Tòa không khớp khu nào thì zone_id NULL,
-- gán tay sau bằng UPDATE.
INSERT INTO towers (code, name, zone_id)
SELECT DISTINCT
       a."Tòa",
       'Tòa ' || a."Tòa",
       z.id
FROM salemate_v1 a
LEFT JOIN zones z ON z.code = upper(substring(a."Tòa" from '^[A-Za-z]+'))
WHERE a."Tòa" IS NOT NULL AND a."Tòa" <> ''
ON CONFLICT (code) DO NOTHING;

-- KIỂM TRA — tòa nào chưa thuộc khu nào:
--   SELECT code FROM towers WHERE zone_id IS NULL;
-- Gán tay ví dụ:
--   UPDATE towers SET zone_id = (SELECT id FROM zones WHERE code='S') WHERE code='S3';
