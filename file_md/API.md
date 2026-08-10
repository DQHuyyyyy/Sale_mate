# API — Backend FastAPI

Base URL `/api`, trả JSON, auth bằng JWT (`Authorization: Bearer <token>`).
Quyền: `public` (không cần token) · `auth` (đăng nhập bất kỳ) · `admin` (chỉ admin).

> **Website mở cho khách vãng lai.** Tìm kiếm căn hộ, chi tiết căn, sơ đồ phân
> khu và chatbot đều xem được mà không cần tài khoản — dependency
> `get_optional_user` trả `None` thay vì ném lỗi khi thiếu token. Token sai hoặc
> hết hạn trên các route này cũng coi như khách, không chặn.
>
> Phần nội bộ vẫn đóng: **tài liệu** (bảng giá, chính sách, hồ sơ pháp lý — kho
> của đội sale), **lịch sử bán**, **quản lý tài khoản**, và mọi thao tác ghi
> (thêm căn hộ, thêm tài liệu, ghi nhận bán).

## Auth
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/api/auth/login` | public | `{username,password}` → `{token,user}`. Token chứa `user_id`,`role`. |
| GET | `/api/auth/me` | auth | Thông tin user hiện tại (để FE chọn menu theo role). |

## Căn hộ  (bảng `salemate_v1` + `apartment_images`)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/api/apartments` | **public** | Tìm kiếm. Params: `tower`, `price_min`, `price_max`, `type`. **Chỉ trả `"Tình trạng"='Còn'`.** Lọc giá theo cột số `gia_tri`. |
| GET | `/api/apartments/{ma_can}` | **public** | Chi tiết 1 căn + danh sách ảnh (sort theo `sort_order`). |
| POST | `/api/apartments` | admin | Thêm căn hộ (ghi `salemate_v1`, kèm ảnh vào `apartment_images` nếu có). |

Ví dụ: `GET /api/apartments?tower=S1&price_min=2&price_max=4&type=1%20PN,%201WC`

Response 1 căn nên gồm cả cột hiển thị (text) lẫn cột số:
`ma_can, toa, tang, so_phong, loai_can, dien_tich, gia (text), gia_tri (số),
huong, view, so_do, noi_that, tinh_trang, images[]`.

## Phân khu  (bảng `zones`, `towers`)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/api/zones` | **public** | Danh sách khu + mô tả (kèm các tòa thuộc khu) cho sơ đồ phân khu. |
| GET | `/api/towers` | **public** | Danh sách tòa, để đổ vào dropdown lọc. |

## Lịch sử bán  (bảng `sales_history`)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/api/sales/my-history` | auth | Căn **do chính người đăng nhập bán**. `sale_id` lấy **từ token**, không từ query. |
| GET | `/api/sales/all` | admin | Tất cả căn đã bán, kèm `full_name` + `username` của sale, `ORDER BY sold_at DESC`. |
| POST | `/api/sales` | auth | Ghi nhận lượt bán: INSERT `sales_history` + UPDATE `salemate_v1."Tình trạng"='Đã bán'`. |

## Quản lý Sale  (bảng `users`)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/api/users?role=sale` | admin | Danh sách tất cả sale, kèm `is_active`. Tài khoản đang hoạt động xếp trước. |
| POST | `/api/users` | admin | Tạo tài khoản sale: `{username, password, full_name, phone?, email?}`. Vai trò backend cố định là `sale` — API này không tạo được admin. Trùng username → 409. |
| PATCH | `/api/users/{id}` | admin | `{is_active}` — bật/tắt tài khoản sale. |

> **Vô hiệu hoá, không xoá.** `sales_history.sale_id` trỏ tới `users(id)`, xoá
> hẳn một sale đã bán căn sẽ vi phạm khoá ngoại và làm mất doanh số của người đó
> khỏi báo cáo. Nên "xoá" ở đây là tắt cờ `is_active`: người đó không đăng nhập
> được nữa, token đang cầm mất hiệu lực ngay lần gọi API kế tiếp, còn lịch sử bán
> vẫn nguyên. Bật lại được bất cứ lúc nào.
>
> Ba giới hạn backend tự chặn: không tự tắt tài khoản của chính mình, không tắt
> tài khoản admin khác, và không tạo được admin qua API.

## Tài liệu  (bảng `documents`)
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| GET | `/api/documents` | auth | Danh sách tài liệu. |
| POST | `/api/documents` | admin | Thêm tài liệu (ghi `documents`). |

## Chatbot
| Method | Path | Quyền | Mô tả |
|---|---|---|---|
| POST | `/api/chat` | **public** | `{message, history}` → `{reply}`. Backend gọi lõi AI ở `AI_CORE_URL`. Có hạn mức: khách **10 lượt/10 phút** theo IP, tài khoản đã đăng nhập **60 lượt/10 phút**. Vượt hạn mức trả **429** kèm `Retry-After`. |

> **Contract cố định** cho `/api/chat`: giữ nguyên input/output. Sau này chỉ thay
> phần lõi (OpenAI → AI Agent Python), frontend không phải sửa.

## Nguyên tắc bảo mật khi implement
- Dependency `get_current_user` (giải mã JWT) + `require_admin` cho route admin.
- `/api/sales/my-history`: `sale_id = current_user.id`, không đọc từ query/body.
- Secrets (`JWT_SECRET`, `OPENAI_API_KEY`, `DATABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`) đọc từ `.env`.
- Upload ảnh (`POST /api/apartments`) và tài liệu (`POST /api/documents`): backend
  đẩy file lên **Supabase Storage** bucket `apartment-images` bằng
  `SUPABASE_SERVICE_ROLE_KEY`, lưu `storage_path`/`file_url` vào DB, rồi trả URL
  hiển thị. Không để service role key lộ ra frontend.
