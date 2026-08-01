# Giaodien.md — Thiết kế & Spec giao diện

> Hướng thiết kế: **portal bất động sản** (kiểu Meey Land) + **trợ lý AI dạng widget nổi**.
> File tham chiếu trực quan: `docs/salesmate_portal.html`.
> Lưu ý: **lõi hành vi chatbot AI đang được thiết kế lại** — tài liệu này đặc tả *giao diện & khung widget*; đặc tả hành vi/agent sẽ cập nhật riêng trong `Core.md` sau.

## 1. Thesis thiết kế

Sản phẩm là **cổng thông tin bất động sản xác thực** cho người mua/bán, môi giới và nhà đầu tư. Giao diện cần:

- Nhấn mạnh **tính xác thực & cập nhật** (pháp lý, quy hoạch, giá) — tín hiệu tin cậy ngay ở hero.
- Cho người dùng **nắm nhịp thị trường trong 2 giây** (panel thống kê theo ngày).
- Bố cục **portal nhiều khối, thẻ (card-based)**, thoáng, nền xám nhạt tách khối.
- **Trợ lý AI** hiện diện dạng **nút nổi góc phải**, mở panel chat — hỗ trợ mà không chiếm trang.

## 2. Design tokens

### Màu

```css
--brand:#1570EF;      /* xanh dương chủ đạo: header, nút, link, icon AI */
--brand-d:#0B4FC0;    /* xanh đậm: gradient hero, nút AI */
--page:#F2F4F7;       /* nền trang */
--card:#FFFFFF;       /* nền thẻ, panel, chat */
--cream:#FAF9F5;      /* nút/nền phụ */
--text:#1D2939;       /* chữ chính */
--muted:#667085;      /* chữ phụ */
--faint:#98A2B3;      /* chữ mờ / placeholder */
--border:#EAECF0; --line:#E4E7EC;
--gold:#F5A623;       /* badge nổi bật / chấm AI */
--new:#E5484D;        /* badge "NEW", giá */
--green:#12B76A;      /* badge "Xác thực" */
--price:#E5484D;      /* màu giá */
```

### Typography

- Font: **Be Vietnam Pro** (400/500/600/700), fallback `system-ui, sans-serif`. Mono: JetBrains Mono cho số liệu.
- Base `16px`, body `400`. H1 hero `26px/600`. H2 section `19px/600`. Nút `14px`. Chú thích `11–12px`.

### Hình khối

- **Bo góc nút: `4px`** (đặc trưng Meey). Thẻ/panel: `10–12px`. Nút tròn AI: `50%`.
- Container nội dung: `max-width 1140px`, canh giữa, padding ngang `20px`.
- Shadow nhẹ cho thẻ; shadow đậm hơn cho search bar và chat panel.

## 3. Cấu trúc trang chủ (thứ tự khối)

1. **Header** (nền `--brand`, sticky): logo · menu ngang (Mua bán nhà đất · Cho thuê · Sang nhượng · Dự án · Tin tức · Bảng giá · Khám phá `NEW`) · icon tim/chuông · "Đăng nhập/Đăng ký" · nút trắng **+ Đăng tin**.
2. **Hero** (gradient xanh): trái = H1 + **thanh tìm kiếm** (chọn khu vực "Toàn quốc" + input + nút tìm) + **banner xác thực** (Pháp lý / Quy hoạch / Giá). Phải = **panel "Thị trường hôm nay"**.
3. **Nhu cầu**: hàng thẻ cuộn ngang (thẻ "Thêm nhu cầu" + các thẻ nhu cầu người dùng).
4. **Bất động sản nổi bật**: tabs (Mua bán / Cho thuê / Sang nhượng) + lưới **thẻ tin đăng**.
5. **Dự án nổi bật**: lưới thẻ dự án.
6. **Footer**: mega-menu link + thông tin công ty + chứng nhận.
7. **Widget AI nổi** (góc dưới phải, phủ mọi trang).

## 4. Component

| Component | Mô tả |
|---|---|
| `Header/Nav` | Nền xanh, menu ngang; ≤960px gập thành drawer trái. Badge `NEW` đỏ. |
| `SearchBar` | Thẻ trắng bo 10px: nút khu vực (có caret) · divider · input · nút tìm vuông xanh. |
| `VerifyBanner` | 3 ô kính mờ trên nền xanh: Xác thực pháp lý / quy hoạch / giá, mỗi ô icon + tiêu đề + phụ đề. |
| `MarketPanel` | Panel kính mờ: "Thị trường hôm nay + ngày", 2 số liệu (tin hiệu lực, tin hôm nay), **biểu đồ cột** theo loại hình + chú giải màu. |
| `DemandCard` | Thẻ nhu cầu: avatar chữ + tên + thời gian + mô tả ngắn. Thẻ "Thêm nhu cầu" nền xanh. |
| `ListingCard` | Thẻ tin đăng: ảnh (placeholder) + badge **Xác thực** (xanh lá) + nút tim + đếm ảnh; tiêu đề 2 dòng; **giá đỏ đậm** + đơn giá tr/m²; meta (diện tích, số PN); dòng vị trí. |
| `ProjectCard` | Ảnh 16:9 + tên dự án + CĐT/vị trí + "Từ **giá**/căn". |
| `Tabs` | Pill bo tròn; tab active nền xanh. |
| `Footer` | 4 cột link + khối thương hiệu + ô chứng nhận. |
| **`AIWidget`** | Xem mục 5. |

## 5. Trợ lý AI (widget) — khung UI

> Hành vi/agent sẽ đặc tả sau. Phần này cố định **khung giao diện**.

### 5.1 Entry point
- Hai nút nổi **góc dưới phải**, xếp dọc: nút **tin nhắn** (trắng) ở trên, nút **AI gradient xanh có ngôi sao ✦** (chấm vàng báo hiệu) ở dưới.
- Bấm nút AI → mở **panel chat** (`376px`, cao ~600px) neo góc phải; ≤560px chuyển **toàn màn hình**.

### 5.2 Cấu trúc panel
- **Header gradient**: avatar ✦ + "Trợ lý AI · SalesMate" + nút đóng ✕.
- **Body** (nền `--page`): lời chào + **4 chip quick-action** (Tư vấn giá theo khu vực · Tìm căn hộ phù hợp · Đặt câu hỏi pháp lý · Viết tin đăng).
- **Composer**: ô nhập placeholder "Tiếp tục cuộc trò chuyện" + **bộ đếm ký tự `x / 2000`** + nút gửi + nút "cuộc trò chuyện mới".

### 5.3 Định dạng hội thoại
- Tin **người dùng**: bong bóng xám, canh phải. Tin **AI**: văn bản canh trái, không bong bóng, render **Markdown** (heading `h4`, bullet, in đậm).
- **Streaming**: hiện 3 chấm "typing" khi đang soạn.
- **Follow-up chips có mũi tên →** dưới mỗi câu trả lời (bấm để hỏi tiếp) — dẫn dắt người dùng.

### 5.4 Ghi chú lõi (chờ cập nhật)
Hành vi trả lời, nguồn dữ liệu, guardrail, HITL… **sẽ do bạn đặc tả sau** và cập nhật trong `Core.md`. Trong prototype hiện tại, phản hồi là **kịch bản mẫu** (đã ghi nhãn), chỉ để minh hoạ khung UI.

## 6. Trạng thái (states)

- **Đang soạn**: typing indicator trong panel.
- **Trống (chat)**: lời chào + 4 quick-action.
- **Lỗi/thiếu dữ liệu**: thông điệp rõ ràng bằng giọng giao diện, tiếng Việt, chỉ cách xử lý.
- Thẻ tin đăng khi thiếu ảnh: placeholder có icon nhà.

## 7. Copy

Tiếng Việt, câu chủ động, sentence case. Nút nói đúng hành động ("+ Đăng tin", "Xem tất cả"). Số liệu/giá format chuẩn VN (3,85 tỷ · 56 tr/m² · 68 m²).

## 8. Responsive

- `>960px`: bố cục đầy đủ, hero 2 cột, lưới tin 4 cột.
- `≤960px`: menu → drawer trái (hamburger); hero 1 cột; lưới tin 2 cột; dự án 2 cột.
- `≤560px`: lưới tin 1 cột; chat widget toàn màn hình; nút "Đăng tin" ẩn chữ.

## 9. Sàn chất lượng

- Focus bàn phím nhìn thấy (`:focus-visible`); tôn trọng `prefers-reduced-motion` (tắt typing/animation).
- `aria-live` cho vùng chat; `role="dialog"` cho panel AI; label cho nút icon.
- Tương phản đạt chuẩn đọc được; chữ đủ lớn để dùng ngoài trời.
