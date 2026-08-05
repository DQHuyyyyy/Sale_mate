# Mô tả Giao diện Dự án — Salemate

## 1. Tổng quan

Giao diện là **trang chủ (Homepage)** của cổng thông tin bất động sản **Salemate** — được định vị là "Cổng thông tin bất động sản xác thực 4.0". Trang được thiết kế theo phong cách hiện đại, chuyên nghiệp, tông màu chủ đạo là **xanh dương (blue)** thể hiện sự tin cậy, uy tín trong lĩnh vực bất động sản.

- **Ngôn ngữ:** Tiếng Việt
- **Loại sản phẩm:** Nền tảng đăng tin, tìm kiếm, giao dịch bất động sản
- **Bố cục:** Chia cột (grid), tối ưu cho màn hình desktop/rộng

---

## 2. Cấu trúc bố cục (Layout)

Trang được chia thành các khối chính theo chiều dọc:

1. **Thanh điều hướng (Header/Navigation Bar)**
2. **Khu vực chính (Hero Section)** — chia 2 cột: bên trái tìm kiếm & banner, bên phải thống kê thị trường
3. **Khu vực nội dung phụ** — "Nhu cầu" và sidebar tiện ích

---

## 3. Thanh điều hướng (Header)

Nằm trên cùng, nền màu xanh dương, gồm:

| Thành phần | Nội dung |
|------------|----------|
| Logo | Biểu tượng chữ "SV" cách điệu  + chữ **Salemate** |
| Menu chính | Mua bán căn hộ · Sơ đồ khu vực · Sang nhượng · Tin tức · Bảng giá · Khám phá `NEW` |
| Icon tiện ích | Biểu tượng ❤️ (yêu thích/lưu tin) và 🔔 (thông báo) |
| Tài khoản | Liên kết **Đăng nhập / Đăng ký** |

Mục "Khám phá" có gắn nhãn `NEW` màu đỏ để thu hút sự chú ý vào tính năng mới.

---

## 4. Khu vực chính (Hero Section)

### 4.1. Cột trái — Tìm kiếm & Banner

- **Tiêu đề lớn:** "Cổng thông tin bất động sản xác thực 4.0" (chữ trắng, đậm, nổi bật trên nền xanh).
- **Thanh tìm kiếm:** Hộp tìm kiếm nền trắng bo góc, gồm:
  - Bộ lọc khu vực: **Toàn quốc** (có icon định vị 📍)
  - Ô nhập từ khóa: placeholder *"Mua nhà chu..."*
  - Nút tìm kiếm 🔍 (icon kính lúp màu xanh)
- **Banner quảng bá:** Hình ảnh các tòa nhà cao tầng làm nền, với dòng chữ **"CỔNG THÔNG TIN BẤT ĐỘNG SẢN XÁC THỰC 4.0"** và 3 nút chức năng "xác thực":
  - ⚖️ **XÁC THỰC PHÁP LÝ**
  - 📍 **XÁC THỰC QUY HOẠCH**
  - 📊 **XÁC THỰC GIÁ**

### 4.2. Cột phải — Thống kê thị trường

Khối nền xanh đậm hơn, hiển thị số liệu thị trường theo thời gian thực:

- **Tiêu đề:** "📈 Thị trường bất động sản hôm nay: **01/08/2026**"
- **Chỉ số nhanh:**
  - Tin đăng đang hiệu lực: **155.246**
  - Tin đăng hôm nay: **5.846**
- **Biểu đồ cột — "Thống kê tin đăng trong ngày":**

| Loại hình | Số lượng | Màu |
|-----------|----------|-----|
| Nhà riêng | 2.500 | Cam |
| Căn hộ chung cư | 1.178 | Xanh dương |
| Đất | 814 | Đỏ/hồng |
| Biệt thự liền kề | 323 | Xanh ngọc |
| Nhà trọ | 150 | Vàng |

Biểu đồ có chú thích (legend) màu tương ứng bên dưới.

---

## 5. Khu vực nội dung phụ

### 5.1. Mục "Nhu cầu"

- Tiêu đề **"Nhu cầu"** kèm liên kết **"Xem tất cả >"** (màu xanh).
- Danh sách các thẻ (card) nhu cầu bất động sản dạng carousel (có thể cuộn ngang, nút mũi tên `>`):
  - Thẻ đầu tiên: **"Thêm nhu cầu BĐS..."** (nền xanh, có nút `+`)
  - Các thẻ tiếp theo hiển thị avatar người đăng + nội dung nhu cầu, ví dụ:
    - "Vốn 420 triệu sở hữu đất nền cửa ngõ thà..."
    - "Vốn từ 400 triệu sở hữu đất nền sổ sẵn k..."
    - "Chủ bán gấp giảm 800 triệu căn shophouse..."
    - "Ngộp bán lô 6m x 19m, giá 1,6 tỷ và 5m..."
    - "Suất nội bộ nền công viên, sổ hồng cầm t..."
    - "Mở bán k đại đô thị Vườn Thơm, Ne..."

### 5.2. Sidebar phải — Tiện ích & Môi giới

- **Khối kêu gọi:** "Trải nghiệm đầy đủ tiện ích và tính năng" + nút **Đăng nhập/Đăng ký MeeyID** (nút xanh nổi bật).
- **Mục "🏆 Môi giới uy tín":** Danh sách môi giới, ví dụ: **Nguyễn Anh Tuấn** (kèm avatar, số tin đăng).

---

## 6. Thành phần nổi (Floating widgets)

Góc dưới bên phải màn hình có các nút nổi:

- Nút hỗ trợ/chat 💬 (biểu tượng trò chuyện)
- Nút tiện ích của Salemate (biểu tượng thương hiệu) ấn vào để chat với AI Agent Salemate

---

## 7. Bảng màu (Color Scheme)

| Vai trò | Màu sắc |
|---------|---------|
| Màu chủ đạo | Xanh dương (`#0066FF` ~ `#1A73E8`) |
| Nền header/hero | Gradient xanh dương |
| Chữ chính trên nền tối | Trắng |
| Nút CTA phụ | Trắng nền, chữ xanh |
| Điểm nhấn | Cam, đỏ, xanh ngọc, vàng (trong biểu đồ) |
| Nhãn NEW | Đỏ |

---

## 8. Nguyên tắc thiết kế (Design Principles)

- **Tin cậy & chuyên nghiệp:** Tông xanh dương, số liệu minh bạch, các nút "xác thực".
- **Ưu tiên tìm kiếm:** Thanh tìm kiếm đặt ngay đầu trang, dễ thao tác.
- **Dữ liệu thời gian thực:** Bảng thống kê thị trường tạo cảm giác nền tảng sống động, cập nhật.
- **Kêu gọi hành động rõ ràng (CTA):** Các nút "Đăng tin", "Đăng nhập/Đăng ký MeeyID" nổi bật.
- **Phản hồi cộng đồng:** Mục "Nhu cầu" và "Môi giới uy tín" tăng tính tương tác, tin cậy.

---

