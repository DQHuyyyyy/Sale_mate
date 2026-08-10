# FRONTEND — React

Frontend chỉ gọi backend qua lớp `src/api`. Không gọi thẳng OpenAI/DB.
Bản mockup giao diện home: `home.html` (giữ đúng phong cách này khi build React —
brand xanh #1570EF, font Be Vietnam Pro, card bo góc, chatbot "S" nổi góc phải).

## Xác thực & phân quyền phía client
- `AuthContext` lưu `user`, `role`, `token`. Sau login gọi `GET /api/auth/me`.
- `ProtectedRoute`: chưa đăng nhập → `/login`; route admin mà `role!=='admin'` → chặn.
  Chỉ bọc **trang nội bộ** — trang công khai không bọc.
- Menu avatar render theo `role` (UX). Backend mới là nơi thực thi bảo mật.

## Khách vãng lai
Website dùng được khi **chưa đăng nhập**: tìm kiếm căn hộ, chi tiết căn + ảnh,
sơ đồ phân khu, và chatbot. Header khi đó hiện nút **"Đăng nhập"** ở góc trên
bên phải — đúng chỗ avatar sẽ xuất hiện sau khi đăng nhập, nên vị trí không nhảy.

Bấm "Đăng nhập" mở **modal nổi ngay trên trang đang xem**, không điều hướng đi
đâu — đăng nhập xong người dùng vẫn ở nguyên chỗ cũ, giỏ lọc và kết quả tìm kiếm
không mất. Đóng bằng nút X, phím Esc, hoặc bấm ra ngoài.

Trang `/login` đầy đủ vẫn giữ cho hai trường hợp: mở thẳng link `/login`, và khi
khách bấm vào trang nội bộ nên `ProtectedRoute` đá về đó — lúc ấy đăng nhập xong
sẽ quay lại đúng trang họ định vào (`state.from`).

Cả hai dùng chung `LoginForm`, chỉ khác vỏ ngoài, nên logic đăng nhập chỉ có một bản.

Mục "Tài liệu" trên nav chỉ hiện với người đã đăng nhập.

## Layout chung
- **Header:** logo SalesMate; nav "Tìm kiếm căn hộ", "Sơ đồ phân khu", "Tài liệu"
  (chỉ khi đã đăng nhập); góc phải là **avatar** hoặc **nút "Đăng nhập"**.
- **Avatar dropdown** (khác theo role):
  - Sale: "Lịch sử bán của tôi", "Profile cá nhân", "Đăng xuất".
  - Admin: "Quản lý Sale", "Căn đã bán toàn hệ thống", "Thêm căn hộ", "Thêm tài liệu",
    "Profile cá nhân", "Đăng xuất" — **KHÔNG** có "Lịch sử bán của tôi".
- **Chatbot "Trợ lý S": sidebar bên phải.** Thu gọn thành nút tròn chữ "S" ở góc
  dưới phải; mở ra chiếm **1/3 chiều ngang**, và **nội dung trang co lại còn 2/3**
  thay vì bị che — vừa xem căn hộ vừa hỏi trợ lý được. Lưới căn hộ tự giảm từ 4
  cột xuống 3. Dưới 1100px thì sidebar phủ lên, nội dung không co nữa.

## Trang (pages)
| Trang | Route | Quyền | Nội dung |
|---|---|---|---|
| Login | `/login` | public | Form đăng nhập. |
| Search (home) | `/` | **public** | Bộ lọc (Tòa + giá 0–20 tỷ + loại căn) + lưới kết quả `salemate_v1` (chỉ 'Còn'). |
| Apartment detail | `/apartments/:maCan` | **public** | Chi tiết căn + gallery ảnh. Nút "Ghi nhận đã bán" chỉ sale thấy. |
| Zones | `/zones` | **public** | Sơ đồ phân khu: khu + mô tả + tòa thuộc khu. |
| Documents | `/documents` | auth | Danh sách tài liệu nội bộ, lọc theo nhóm. |
| MySales | `/my-sales` | sale | Lịch sử bán của chính mình (chỉ Sale). |
| Profile | `/profile` | auth | Trang cá nhân của người đăng nhập. |
| Admin – Sales | `/admin/sales` | admin | Danh sách sale + căn đã bán toàn hệ thống (tên+username, sắp theo thời gian). |
| Admin – Add Apartment | `/admin/apartments/new` | admin | Form thêm căn hộ (+ ảnh). |
| Admin – Add Document | `/admin/documents/new` | admin | Form thêm tài liệu. |

## Component chính
- `Header`, `AvatarMenu` (menu theo role).
- `LoginForm` — ruột màn đăng nhập; `LoginModal` — vỏ modal nổi trên trang.
- `SearchFilters` — dropdown Tòa, 2 ô giá (0–20), dropdown loại căn.
- `ApartmentCard` — ảnh (từ `apartment_images`), badge "Còn", mã căn, giá, loại căn,
  diện tích, tòa+tầng, hướng, view, sổ đỏ, nội thất.
- `ApartmentList`, `ApartmentDetail` (đầy đủ thông tin + gallery ảnh).
- `ZoneList` — thẻ từng phân khu.
- `SaleTable`, `SoldTable` (khu vực admin).
- `AddApartmentForm`, `AddDocumentForm`.
- `ChatSidebar` — sidebar phải, gọi `POST /api/chat`. Trạng thái mở nằm ở
  `Layout` vì cả sidebar lẫn phần nội dung cùng cần biết (nội dung phải co lại).
  Backend trả **429** khi hỏi quá nhanh — hiện nguyên văn câu báo cho người dùng.
- `ProtectedRoute`.

## Lớp gọi API (src/api)
Client chung tự gắn `Authorization`. Hàm: `login`, `getMe`, `searchApartments`,
`getApartment`, `getZones`, `getMySales`, `getAllSales`, `getSales`,
`addApartment`, `addDocument`, `sendChatMessage`.

## Lưu ý UX
- Giá: 2 ô số hoặc slider đôi, giới hạn 0–20.
- Kết quả rỗng: "Không có căn phù hợp với bộ lọc".
- Ảnh: hiển thị theo `image_url` trong `apartment_images` (public URL từ Supabase
  Storage bucket `apartment-images`, hoặc link cũ). Không gọi Supabase bằng service
  role ở frontend — chỉ nhận URL từ backend.
- Chatbot giữ lịch sử hội thoại trong state để gửi kèm mỗi lượt.
