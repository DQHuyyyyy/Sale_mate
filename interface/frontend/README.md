# SalesMate — Frontend (React + Vite)

Giao diện cho nhân viên sale và quản trị viên. Bám phong cách mockup
`file_md/home.html`: brand xanh `#1570EF`, font Be Vietnam Pro, card bo góc,
chatbot "S" nổi góc dưới phải.

## Chạy

```bash
cd interface/frontend
npm install
npm run dev          # http://localhost:5173
```

Backend phải chạy sẵn ở `http://localhost:8000` — `vite.config.js` đã proxy
`/api` sang đó nên không vướng CORS. Khi deploy, đặt `VITE_API_BASE_URL` trong
`.env.local` (xem `.env.example`).

`npm run build` để dựng bản production vào `dist/`.

## Cấu trúc

```
src/
├── api/          client.js (fetch + JWT + dịch lỗi) · index.js (mọi hàm gọi API)
├── context/      AuthContext — user, role, token, signIn/signOut
├── components/   Header · AvatarMenu · ProtectedRoute · Layout · ChatbotWidget
│                 SearchFilters · ApartmentCard · ApartmentList · ZoneList
│                 SaleTable · SoldTable · DocumentList
│                 AddApartmentForm · AddDocumentForm · AddSaleForm · Icons
├── pages/        Login · Home · Search · Zones · ApartmentDetail · Documents
│                 MySales · Profile
│                 admin/AdminSales · admin/AddApartment · admin/AddDocument
├── utils/        format.js — giá, diện tích, ngày giờ kiểu Việt
└── styles/       global.css — toàn bộ token màu/bo góc/bóng

public/
└── media/        ảnh + video giới thiệu dự án cho trang chủ (bản gốc ở /data)
```

## Route

| Route | Quyền | Trang |
|---|---|---|
| `/login` | public | Đăng nhập |
| `/` | public | Trang chủ — giới thiệu Ocean Park 1/2/3, ảnh và video dự án |
| `/tim-kiem` | public | Tìm kiếm căn hộ (chỉ căn "Còn") |
| `/zones` | public | Sơ đồ phân khu |
| `/documents` | auth | Danh sách tài liệu, lọc theo nhóm |
| `/apartments/:maCan` | auth | Chi tiết căn + gallery ảnh; sale ghi nhận đã bán ở đây |
| `/my-sales` | sale | Lịch sử bán của tôi |
| `/profile` | auth | Profile cá nhân |
| `/admin/sales` | admin | Quản lý tài khoản sale (tạo, bật/tắt) + căn đã bán toàn hệ thống |
| `/admin/apartments/new` | admin | Thêm căn hộ |
| `/admin/documents/new` | admin | Thêm tài liệu |

## Quy tắc

- **Không có secret nào trong frontend.** Mọi biến `VITE_*` đều nằm trong bundle
  ai cũng đọc được — không đặt `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
  `JWT_SECRET`, `OPENAI_API_KEY` ở đây.
- **Không gọi thẳng OpenAI hay Supabase.** Mọi thứ đi qua backend; ảnh chỉ hiển
  thị từ URL do backend trả về.
- `ProtectedRoute` và menu theo role chỉ là trải nghiệm. Bảo mật thật nằm ở
  backend.
- Màu/bo góc/font lấy từ biến trong `styles/global.css`, không hardcode trong
  component.
- Chữ tiếng Việt, câu chủ động, sentence case. Báo lỗi phải nói được cách khắc phục.
