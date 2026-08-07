# Deploy — SalesMate

Bản này dựng **một môi trường chạy từ nhánh `develop`, chi phí 0đ**, đủ cho
khoảng 10 người dùng thử. Chạy máy mình thì xem [RUN.md](RUN.md).

> **Vì sao chưa deploy `main`.** Nhánh `main` đang là bản 05/08, lạc hậu 33
> commit và **chưa có thư mục `interface/`** — trỏ service vào đó là build hỏng
> ngay. Toàn bộ code đang sống trên `develop`. Xem
> [mục cuối](#khi-nào-muốn-thêm-môi-trường-production) khi muốn thêm production.

## Cái gì nằm ở đâu

| | Địa chỉ | Nền tảng |
|---|---|---|
| Giao diện | `salesmate….vercel.app` | Vercel — nhánh `develop` |
| API sản phẩm | `salesmate-api-dev.onrender.com` | Render — nhánh `develop` |
| Lõi AI | `salesmate-ai-core.onrender.com` | Render — nhánh `develop` |
| Database | Supabase project `salesmate` | Supabase |

Lõi AI chỉ dựng một bản vì nó không giữ trạng thái — RAG đang tắt
([bootstrap.py](src/bootstrap.py#L29)) và lịch sử chat do API gửi kèm mỗi
request. Hai bản chỉ tổ thêm một lần chờ khởi động.

Toàn bộ khai báo Render nằm trong [render.yaml](render.yaml), không phải bấm tay
từng service.

### Database dùng chung — hệ quả cần biết

Hai môi trường trỏ vào **cùng một Supabase project**. Đổi lại sự đơn giản, có ba
điều phải nhớ:

- **Team sửa dữ liệu ở dev là người dùng thấy ngay ở production.** Xoá một căn
  hộ để thử tính năng thì căn đó biến mất khỏi trang người dùng đang xem.
- **Chạy migration là chạy thẳng lên production.** Không có nơi diễn tập. Đọc kỹ
  file SQL trước khi dán vào SQL Editor, và chạy hai câu KIỂM TRA ghi trong
  `001_alter_salemate_v1.sql`.
- **Tài khoản dùng chung.** `admin` và `sale01` đăng nhập được ở cả hai nơi.
  Riêng token thì không dùng chéo được vì `JWT_SECRET` mỗi service một chuỗi.

Muốn thử thứ gì có thể hỏng dữ liệu thì tạo bản ghi riêng để test (mã căn đặt
tiền tố dễ nhận, ví dụ `TEST-001`) rồi xoá sau, thay vì sửa dữ liệu thật.

## Vì sao có repo thứ hai

Render không cài được GitHub App lên org `AI20K-Build-Phase-Cohort-3` — chủ sở
hữu org đã tắt cả việc cài lẫn việc thành viên gửi yêu cầu. Nên có một **bản sao
để deploy** ở tài khoản cá nhân:

| Repo | Vai trò | Ai đẩy |
|---|---|---|
| `AI20K-Build-Phase-Cohort-3/P-055` | **Nguồn sự thật.** Mọi commit, PR, review đều ở đây | cả team |
| `DQHuyyyyy/Sale_mate` | **Bản sao một chiều.** Chỉ để Render đọc | chỉ huy, bằng `make sync-deploy` |

> **Không commit vào repo mirror.** BTC chấm tiến độ bằng git history ở repo org
> — commit lạc sang mirror là commit không ai tính. Mirror không nhận PR, không
> nhận review, và có thể bị ghi đè bất cứ lúc nào.

### Cài một lần

```bash
git remote add deploy https://github.com/DQHuyyyyy/Sale_mate.git
```

### Mỗi lần muốn đưa code mới lên server

```bash
make sync-deploy
```

Lệnh này lấy `main` và `develop` mới nhất **từ repo org** rồi đẩy sang mirror.
Nó đẩy thẳng `origin/<nhánh>` chứ không qua nhánh local, nên bạn không cần
checkout hay pull trước — kết quả luôn đúng thứ đang nằm trên repo org.

```
Mirror: https://github.com/DQHuyyyyy/Sale_mate.git
  main: da dong bo
  develop: mirror thieu 3 commit -> dang day...
```

Đẩy xong Render tự build lại nhánh vừa đổi. Chạy lại lúc không có gì mới cũng
không sao, nó chỉ báo "da dong bo".

**Nhớ chạy sau mỗi lần merge PR.** Merge xảy ra trên máy chủ GitHub, không qua
máy ai cả — quên sync thì Render vẫn phục vụ code cũ và **không báo lỗi gì**.
Trang chạy bình thường, chỉ là cũ. Đây là cách hỏng khó nhận ra nhất của mô hình
này.

## Thứ tự bắt buộc

Ba giá trị phụ thuộc chéo nhau, làm sai thứ tự là phải quay lại sửa:

```
Render deploy trước  →  có URL API
       ↓
Vercel deploy sau, điền VITE_API_BASE_URL = URL API
       ↓
Quay lại Render, điền CORS_ORIGINS = URL Vercel
```

Lần deploy Render đầu tiên sẽ **báo lỗi CORS cho tới bước cuối** — đó là bình
thường, không phải hỏng.

---

## Bước 1 — Render

Trước hết chạy `make sync-deploy` để mirror có sẵn `main` và `develop`, rồi cài
Render GitHub App lên tài khoản `DQHuyyyyy` và cho nó quyền đọc `Sale_mate`.

**Dashboard → New → Blueprint → chọn repo `Sale_mate`.** Ô **Branch** ở màn hình
này chỉ nói cho Render biết *đọc file `render.yaml` ở nhánh nào* — chọn `develop`
hay `main` đều được, miễn nhánh đó đã có file. Nhánh mà từng service deploy thì
lấy từ chính `render.yaml`, không phải từ ô này.

Render dựng hai service, cả hai đều theo nhánh `develop`, và hỏi các biến
`sync: false` của `salesmate-api-dev`:

| Biến | Giá trị |
|---|---|
| `DATABASE_URL` | Supabase → Connection string → **Transaction pooler** |
| `SUPABASE_URL` | Supabase → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | cùng trang |
| `CORS_ORIGINS` | *để trống, điền ở bước 3* |
| `AI_CORE_URL` | `https://salesmate-ai-core.onrender.com` |

`JWT_SECRET` Render tự sinh, không phải nhập.

Với `salesmate-ai-core`, `OPENAI_API_KEY` bỏ trống cũng chạy: hệ thống rơi về
`ScriptedProvider`, chat trả lời theo kịch bản thay vì gọi model thật. Điền key
vào khi muốn chat thật.

Deploy xong, kiểm tra từng cái:

```bash
curl https://salesmate-api-dev.onrender.com/api/health
# {"status":"ok","storage_enabled":true,"chat_enabled":true}

curl https://salesmate-ai-core.onrender.com/health
```

Lần gọi đầu chờ khoảng 50 giây — service đang ngủ dậy. Xem mục cuối.

## Bước 2 — Vercel

**Add New → Project → chọn repo này**, rồi đặt:

| Mục | Giá trị |
|---|---|
| Root Directory | `interface/frontend` ← quan trọng, repo là monorepo |
| Framework Preset | Vite (Vercel tự nhận) |
| Production Branch | **`develop`** ← không phải `main` |

Production Branch phải là `develop` vì cùng lý do với Render: `main` không có
`interface/frontend`, chỉ có `frontend/` ở gốc, nên build từ `main` sẽ hỏng. Đặt
`develop` thì người test có một URL ngắn gọn (`salesmate.vercel.app`) thay vì URL
preview dài loằng ngoằng.

Build command và output directory đã khai trong
[interface/frontend/vercel.json](interface/frontend/vercel.json), khỏi điền.

**Environment Variables** — đặt `VITE_API_BASE_URL` cho **cả Production lẫn
Preview**, cùng một giá trị:

```
https://salesmate-api-dev.onrender.com
```

Đây là chỗ dùng đến biến khai trong
[interface/frontend/.env.example](interface/frontend/.env.example). Ở máy mình
nó để trống vì `vite.config.js` proxy hộ; trên Vercel **không có proxy** — chỉ
có file tĩnh — nên phải trỏ tuyệt đối.

## Bước 3 — Nối dây CORS

Quay lại Render, điền `CORS_ORIGINS` cho `salesmate-api-dev` rồi để nó tự deploy
lại. Giá trị là URL Vercel vừa có ở bước 2:

```
https://salesmate.vercel.app
```

Nhiều domain thì ngăn bằng dấu phẩy, không có khoảng trắng — hữu ích khi bạn
muốn cho phép cả URL preview của các nhánh khác.
[main.py](interface/backend/app/main.py#L60) đọc đúng danh sách này — sai một ký
tự là trình duyệt chặn hết, trong khi `curl` vẫn chạy ngon. Gặp lỗi CORS thì
kiểm tra biến này trước tiên.

## Bước 4 — Tài khoản cho người test

```bash
cd interface/backend
python scripts/seed_users.py
```

Nhập username/mật khẩu, script in ra SQL — dán vào Supabase SQL Editor. Chỉ có
một project nên không phải chọn. Mật khẩu hash bằng bcrypt, không lưu ở đâu dạng
thô, nên quên là phải tạo lại.

## Khi nào muốn thêm môi trường production

Điều kiện cần: **`main` đã có thư mục `interface/`**, tức là đã merge `develop`
vào `main`. Trước đó thì mọi service trỏ vào `main` đều build hỏng.

Merge xong, sửa [render.yaml](render.yaml): copy khối `salesmate-api-dev`, đổi
`name` thành `salesmate-api` và `branch` thành `main`. Đặt `CORS_ORIGINS` của nó
bằng URL production Vercel. Bên Vercel đổi Production Branch về `main`, và tách
`VITE_API_BASE_URL` thành hai giá trị — Production trỏ `salesmate-api`, Preview
trỏ `salesmate-api-dev`.

Cân nhắc có nên tách luôn Supabase khi đó không. Lúc chỉ có một môi trường thì
dùng chung một database không sao; khi người dùng thật ở production còn team vẫn
nghịch ở dev thì rủi ro khác hẳn.

---

## Sống chung với free tier

**Render ngủ sau 15 phút không ai gọi.** Request đánh thức nó mất khoảng 50
giây, các request sau thì nhanh bình thường. Với 10 người dùng thử, đây là điều
duy nhất họ sẽ phàn nàn.

Cách xử lý thực tế:

- **Trước buổi test, đánh thức thủ công** — mở
  `https://salesmate-api-dev.onrender.com/api/health` và
  `https://salesmate-ai-core.onrender.com/health` trước 1 phút. Đơn giản nhất và
  không tốn gì.
- **Nói trước với người test** rằng lần vào đầu tiên chờ khoảng một phút. Biết
  trước thì họ đợi; không biết thì họ tưởng web hỏng và đóng tab.
- **Ping tự động thì bạn không làm được bằng GitHub Actions** — org đang bị chặn
  Actions vì billing, cả ba CI phải chạy nhờ self-hosted runner của BTC
  ([ci-ai-core.yml](.github/workflows/ci-ai-core.yml#L27-L29)). Dịch vụ ping bên
  ngoài như UptimeRobot thì được, nhưng đó là lách chính sách Render.
- **Hết chịu nổi thì nâng riêng `salesmate-api-dev` lên Starter (~$7/tháng)** —
  chỉ cần đổi `plan: free` thành `plan: starter` trong `render.yaml`. Lõi AI vẫn
  để free, chỉ chat mới phải chờ.

**Chuỗi đánh thức cộng dồn.** Người dùng mở chat lần đầu: API dậy (~50s) rồi mới
gọi lõi AI, lõi AI lại dậy tiếp (~50s). Đánh thức trước cả hai là tránh được.

**Build đầu tiên trên Render lâu** (5–10 phút) vì phải cài `psycopg`. Các lần
sau có cache, nhanh hơn nhiều.

## Bảng biến môi trường

Không biến nào nằm trong git. Máy mình đọc từ `.env` ở gốc repo; trên Render và
Vercel thì nhập trong dashboard.

| Biến | Đặt ở đâu | Ghi chú |
|---|---|---|
| `DATABASE_URL` | `salesmate-api-dev` | Transaction pooler của Supabase |
| `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` | `salesmate-api-dev` | service role bỏ qua RLS — không bao giờ đưa ra frontend |
| `SUPABASE_BUCKET` | `salesmate-api-dev` | đã có sẵn trong `render.yaml` |
| `JWT_SECRET` | Render tự sinh | ≥32 ký tự, không phải nhập |
| `CORS_ORIGINS` | `salesmate-api-dev` | URL Vercel |
| `AI_CORE_URL` | `salesmate-api-dev` | trỏ về `salesmate-ai-core` |
| `OPENAI_API_KEY` | `salesmate-ai-core` | bỏ trống → chat chạy kịch bản |
| `VITE_API_BASE_URL` | Vercel | Production và Preview cùng giá trị |
