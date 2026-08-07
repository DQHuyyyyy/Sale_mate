# Deploy — SalesMate

Bản này dựng **hai môi trường, chi phí 0đ**, đủ cho khoảng 10 người dùng thử.
Chạy máy mình thì xem [RUN.md](RUN.md).

## Cái gì nằm ở đâu

| | Production (user test) | Development (team) | Nền tảng |
|---|---|---|---|
| Giao diện | `salesmate.vercel.app` | `salesmate-git-develop-….vercel.app` | Vercel — nhánh `main` / `develop` |
| API sản phẩm | `salesmate-api.onrender.com` | `salesmate-api-dev.onrender.com` | Render — nhánh `main` / `develop` |
| Lõi AI | `salesmate-ai-core.onrender.com` | *dùng chung với production* | Render — nhánh `main` |
| Database | Supabase project `salesmate` | Supabase project `salesmate-dev` | Supabase |

Lõi AI chỉ dựng một bản vì nó không giữ trạng thái — RAG đang tắt
([bootstrap.py](src/bootstrap.py#L29)) và lịch sử chat do API gửi kèm mỗi
request. Hai bản chỉ tổ thêm một lần chờ khởi động.

Toàn bộ khai báo Render nằm trong [render.yaml](render.yaml), không phải bấm tay
từng service.

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

## Bước 1 — Supabase cho dev

Tạo project thứ hai tên `salesmate-dev` (free tier cho 2 project). Chạy lại bốn
file trong [interface/backend/migrations/](interface/backend/migrations/) theo
đúng thứ tự 001 → 004, giống lần dựng production.

Đừng dùng chung một database cho cả hai môi trường. Team sửa dữ liệu hàng ngày
sẽ ghi đè đúng thứ mà người dùng đang xem.

> Project free bị **tạm dừng sau 7 ngày không ai gọi**. Cái dev sẽ hay ngủ —
> đánh thức bằng một nút trong dashboard Supabase, dữ liệu không mất.

## Bước 2 — Render

Trước hết chạy `make sync-deploy` để mirror có sẵn `main` và `develop`, rồi cài
Render GitHub App lên tài khoản `DQHuyyyyy` và cho nó quyền đọc `Sale_mate`.

**Dashboard → New → Blueprint → chọn repo `Sale_mate`.** Render đọc `render.yaml`
và dựng cả ba service. Nó sẽ hỏi các biến `sync: false`:

| Biến | `salesmate-api` | `salesmate-api-dev` |
|---|---|---|
| `DATABASE_URL` | Supabase **production** → Connection string → **Transaction pooler** | Supabase **dev** |
| `SUPABASE_URL` | project production | project dev |
| `SUPABASE_SERVICE_ROLE_KEY` | project production | project dev |
| `CORS_ORIGINS` | *để trống, điền ở bước 4* | *để trống* |
| `AI_CORE_URL` | `https://salesmate-ai-core.onrender.com` | cùng giá trị |

`JWT_SECRET` Render tự sinh, mỗi service một chuỗi khác nhau — nhờ vậy token cấp
ở dev không dùng được trên production.

Với `salesmate-ai-core`, `OPENAI_API_KEY` bỏ trống cũng chạy: hệ thống rơi về
`ScriptedProvider`, chat trả lời theo kịch bản thay vì gọi model thật. Điền key
vào khi muốn chat thật.

Deploy xong, kiểm tra từng cái:

```bash
curl https://salesmate-api.onrender.com/api/health
# {"status":"ok","storage_enabled":true,"chat_enabled":true}

curl https://salesmate-ai-core.onrender.com/health
```

Lần gọi đầu chờ khoảng 50 giây — service đang ngủ dậy. Xem mục cuối.

## Bước 3 — Vercel

**Add New → Project → chọn repo này**, rồi đặt:

| Mục | Giá trị |
|---|---|
| Root Directory | `interface/frontend` ← quan trọng, repo là monorepo |
| Framework Preset | Vite (Vercel tự nhận) |
| Production Branch | `main` |

Build command và output directory đã khai trong
[interface/frontend/vercel.json](interface/frontend/vercel.json), khỏi điền.

**Environment Variables** — đặt `VITE_API_BASE_URL` **hai lần, khác giá trị**:

| Environment | Giá trị |
|---|---|
| Production | `https://salesmate-api.onrender.com` |
| Preview | `https://salesmate-api-dev.onrender.com` |

Đây là chỗ dùng đến biến khai trong
[interface/frontend/.env.example](interface/frontend/.env.example). Ở máy mình
nó để trống vì `vite.config.js` proxy hộ; trên Vercel **không có proxy** — chỉ
có file tĩnh — nên phải trỏ tuyệt đối.

Không cần tạo project Vercel thứ hai: mọi nhánh không phải `main` tự có URL
preview, và nhánh `develop` giữ nguyên một URL cố định dạng
`salesmate-git-develop-<team>.vercel.app`. Đó là môi trường dev của bạn.

## Bước 4 — Nối dây CORS

Quay lại Render, điền `CORS_ORIGINS` rồi để nó tự deploy lại:

| Service | `CORS_ORIGINS` |
|---|---|
| `salesmate-api` | `https://salesmate.vercel.app` |
| `salesmate-api-dev` | `https://salesmate-git-develop-<team>.vercel.app` |

Nhiều domain thì ngăn bằng dấu phẩy, không có khoảng trắng.
[main.py](interface/backend/app/main.py#L60) đọc đúng danh sách này — sai một ký
tự là trình duyệt chặn hết, trong khi `curl` vẫn chạy ngon. Gặp lỗi CORS thì
kiểm tra biến này trước tiên.

## Bước 5 — Tài khoản cho người test

```bash
cd interface/backend
python scripts/seed_users.py
```

Nhập username/mật khẩu, script in ra SQL — dán vào Supabase SQL Editor của
**đúng project** (prod hay dev). Mật khẩu hash bằng bcrypt, không lưu ở đâu
dạng thô, nên quên là phải tạo lại.

---

## Sống chung với free tier

**Render ngủ sau 15 phút không ai gọi.** Request đánh thức nó mất khoảng 50
giây, các request sau thì nhanh bình thường. Với 10 người dùng thử, đây là điều
duy nhất họ sẽ phàn nàn.

Cách xử lý thực tế:

- **Trước buổi test, đánh thức thủ công** — mở
  `https://salesmate-api.onrender.com/api/health` trước 1 phút. Ba service thì
  mở cả ba. Đơn giản nhất và không tốn gì.
- **Nói trước với người test** rằng lần vào đầu tiên chờ khoảng một phút. Biết
  trước thì họ đợi; không biết thì họ tưởng web hỏng và đóng tab.
- **Ping tự động thì bạn không làm được bằng GitHub Actions** — org đang bị chặn
  Actions vì billing, cả ba CI phải chạy nhờ self-hosted runner của BTC
  ([ci-ai-core.yml](.github/workflows/ci-ai-core.yml#L27-L29)). Dịch vụ ping bên
  ngoài như UptimeRobot thì được, nhưng đó là lách chính sách Render.
- **Hết chịu nổi thì nâng riêng `salesmate-api` lên Starter (~$7/tháng)** — chỉ
  cần đổi `plan: free` thành `plan: starter` trong `render.yaml`. Dev và lõi AI
  vẫn để free.

**Chuỗi đánh thức cộng dồn.** Người dùng mở chat lần đầu: API dậy (~50s) rồi mới
gọi lõi AI, lõi AI lại dậy tiếp (~50s). Đánh thức trước cả hai là tránh được.

**Build đầu tiên trên Render lâu** (5–10 phút) vì phải cài `psycopg`. Các lần
sau có cache, nhanh hơn nhiều.

## Bảng biến môi trường

Không biến nào nằm trong git. Máy mình đọc từ `.env` ở gốc repo; trên Render và
Vercel thì nhập trong dashboard.

| Biến | Đặt ở đâu | Ghi chú |
|---|---|---|
| `DATABASE_URL` | Render (2 API) | Transaction pooler của Supabase |
| `SUPABASE_URL` · `SUPABASE_SERVICE_ROLE_KEY` | Render (2 API) | service role bỏ qua RLS — không bao giờ đưa ra frontend |
| `SUPABASE_BUCKET` | Render (2 API) | đã có sẵn trong `render.yaml` |
| `JWT_SECRET` | Render tự sinh | ≥32 ký tự, khác nhau giữa prod và dev |
| `CORS_ORIGINS` | Render (2 API) | URL Vercel tương ứng |
| `AI_CORE_URL` | Render (2 API) | trỏ về `salesmate-ai-core` |
| `OPENAI_API_KEY` | Render (lõi AI) | bỏ trống → chat chạy kịch bản |
| `VITE_API_BASE_URL` | Vercel | đặt riêng cho Production và Preview |
