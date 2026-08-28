# Deploy — SalesMate

Bản này dựng **một môi trường chạy từ nhánh `develop`, chi phí 0đ**, đủ cho
khoảng 10 người dùng thử. Chạy máy mình thì xem [docs/RUN.md](docs/RUN.md).

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

| Repo | Nhánh | Vai trò | Ai đẩy |
|---|---|---|---|
| `AI20K-Build-Phase-Cohort-3/P-055` | `main` ← `develop` ← nhánh cá nhân | **Nguồn sự thật.** Mọi commit, PR, review đều ở đây | cả team |
| `DQHuyyyyy/Sale_mate` | **chỉ `develop`** | **Bản sao một chiều.** Chỉ để Render và Vercel đọc | chỉ huy, bằng `make sync-deploy` |

Mirror **cố ý chỉ giữ một nhánh**, và `develop` là nhánh mặc định của nó. Phân
cấp `main ← develop` không có ý nghĩa gì ở một repo không ai làm việc trong đó,
trong khi một nhánh `main` cũ nằm đấy thì gây hại thật: Render và Vercel mặc
định nhìn vào nó, thấy cây file chưa có `interface/` và build hỏng.

> **Không commit vào repo mirror.** BTC chấm tiến độ bằng git history ở repo org
> — commit lạc sang mirror là commit không ai tính. Mirror không nhận PR, không
> nhận review, và có thể bị ghi đè bất cứ lúc nào.

### Cài một lần

```bash
git remote add deploy https://github.com/DQHuyyyyy/Sale_mate.git
```

Trên GitHub, đặt `develop` làm **Default branch** của `Sale_mate` (Settings →
General), rồi xoá nhánh `main` khỏi mirror.

### Mỗi lần muốn đưa code mới lên server

```bash
make sync-deploy
```

Lệnh này lấy `develop` mới nhất **từ repo org** rồi đẩy sang mirror. Nó đẩy
thẳng `origin/develop` chứ không qua nhánh local, nên bạn không cần checkout hay
pull trước — kết quả luôn đúng thứ đang nằm trên repo org.

```
Mirror: https://github.com/DQHuyyyyy/Sale_mate.git
  develop: mirror thieu 3 commit -> dang day...
```

Danh sách nhánh cần đẩy nằm ở hằng `BRANCHES` trong
[scripts/sync_deploy.py](scripts/sync_deploy.py).

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

Trước hết chạy `make sync-deploy` để mirror có nhánh `develop`, rồi cài Render
GitHub App lên tài khoản `DQHuyyyyy` và cho nó quyền đọc `Sale_mate`.

**Dashboard → New → Blueprint → chọn repo `Sale_mate`.** Ô **Branch** ở màn hình
này chỉ nói cho Render biết *đọc file `render.yaml` ở nhánh nào* — chọn
`develop`. Nhánh mà từng service deploy thì lấy từ chính `render.yaml`, không
phải từ ô này.

Render dựng hai service, cả hai đều theo nhánh `develop`, và hỏi các biến
`sync: false` của `salesmate-api-dev`:

| Biến | Giá trị |
|---|---|
| `DATABASE_URL` | Supabase → Connection string → **Transaction pooler** |
| `SUPABASE_URL` | Supabase → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | cùng trang |
| `CORS_ORIGINS` | *để trống, điền ở bước 3* |
| `AI_CORE_URL` | `https://salesmate-ai-core.onrender.com` |
| `AI_CORE_API_KEY` | chuỗi tự sinh, **dán y hệt sang `salesmate-ai-core`** |

`JWT_SECRET` Render tự sinh, không phải nhập.

Sinh `AI_CORE_API_KEY` một lần rồi dán vào **cả hai** service:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

⚠️ Với `salesmate-ai-core`, **`OPENAI_API_KEY` là bắt buộc**. Bỏ trống thì
service **không khởi động** — `bootstrap.py` ném `ConfigurationError`, và Render
sẽ báo deploy hỏng. Đường rơi về `ScriptedProvider` đã bị bỏ vì nó hỏng câm:
`FakeEmbedder` sinh vector 64 chiều ghi vào collection 1536 chiều nên truy hồi
luôn rỗng mà không báo lỗi, còn người dùng thì nhận nội dung soạn sẵn tưởng là
thật.

`ANTHROPIC_API_KEY` thì ngược lại — thiếu vẫn chạy đủ, chỉ tắt nhánh leo thang.

Deploy xong, kiểm tra từng cái:

```bash
curl https://salesmate-api-dev.onrender.com/api/health
# {"status":"ok","storage_enabled":true,"chat_enabled":true}

curl https://salesmate-ai-core.onrender.com/health
```

Lần gọi đầu chờ khoảng 50 giây — service đang ngủ dậy. Xem mục cuối.

## Bước 2 — Vercel

**Điều kiện: mirror phải đã lấy `develop` làm nhánh mặc định** (xem mục repo thứ
hai ở trên). Màn hình New Project của Vercel luôn import từ nhánh mặc định và
**không cho đổi ở bước đó** — Production Branch chỉ sửa được sau khi project đã
tồn tại. Nếu mặc định còn là `main`, Vercel đọc cây file của `main`: Root
Directory không chọn được `interface/frontend` vì nó không tồn tại ở đó, và
preset bị đoán nhầm thành FastAPI do gốc repo có `requirements.txt` với `src/`.

**Add New → Project → chọn `Sale_mate`**:

| Mục | Giá trị |
|---|---|
| Root Directory | `interface/frontend` ← quan trọng, repo là monorepo |
| Framework Preset | Vite — tự nhận đúng sau khi đặt Root Directory |

Người test sẽ có URL ngắn gọn dạng `sale-mate.vercel.app` vì `develop` giờ là
nhánh production của Vercel.

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
lại. Giá trị là **URL Vercel vừa có ở bước 2**, copy nguyên văn từ dashboard
Vercel — dạng `https://<ten-project>.vercel.app`, ví dụ:

```
https://sale-mate.vercel.app
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

Merge xong, thêm `"main"` vào hằng `BRANCHES` trong
[scripts/sync_deploy.py](scripts/sync_deploy.py) rồi chạy `make sync-deploy` để
mirror có nhánh đó.

Tiếp theo sửa [render.yaml](render.yaml): copy khối `salesmate-api-dev`, đổi
`name` thành `salesmate-api` và `branch` thành `main`. Đặt `CORS_ORIGINS` của nó
bằng URL production Vercel. Bên Vercel đổi Production Branch về `main`, và tách
`VITE_API_BASE_URL` thành hai giá trị — Production trỏ `salesmate-api`, Preview
trỏ `salesmate-api-dev`.

Cân nhắc có nên tách luôn Supabase khi đó không. Lúc chỉ có một môi trường thì
dùng chung một database không sao; khi người dùng thật ở production còn team vẫn
nghịch ở dev thì rủi ro khác hẳn.

---

## Sống chung với free tier

**Render ngủ sau 15 phút không có lưu lượng.** Đánh thức mất 30–60 giây. Với
người dùng thử, đây là điều duy nhất họ sẽ phàn nàn.

### Chỉ có MỘT cách chữa: lưu lượng từ BÊN NGOÀI Render

Đo được ngày 22/08/2026, cùng một URL `ai-core/health`:

| Gọi từ | Kết quả |
|---|---|
| máy ngoài | **200** sau 42 giây — Render dựng container thật |
| `salesmate-api-dev` (trong Render) | **502 / 429** sau chưa tới 5 giây, không đánh thức gì |

Thời gian là bằng chứng: đánh thức thật thì Render **giữ request lại ~50 giây**.
Bật ra sau 5 giây nghĩa là nó từ chối ngay, không hề bắt đầu.

**Hệ quả: backend KHÔNG đánh thức hộ lõi AI được.** Đã thử ba cách — ping lúc
khởi động, endpoint `/api/chat/danh-thuc`, vòng lặp nền mỗi 5 phút — cả ba đều
chạy trong Render nên đều vô hiệu. Chúng đã bị gỡ; đừng dựng lại.

**Health check của Render cũng không tính.** Log cho thấy `/api/health` bị gọi
mỗi 5 giây từ IP nội bộ `10.237.x.x`, rồi service vẫn `Shutting down`. Đồng hồ
15 phút chỉ đếm lưu lượng đi vào từ Internet.

### Cấu hình bắt buộc: hai job cron ngoài

[cron-job.org](https://cron-job.org) — miễn phí, chọn được khung giờ, và chạy
đúng giờ hơn cron của GitHub Actions (Actions trễ 5–20 phút khi hệ thống bận, mà
ngưỡng ngủ chỉ 15 phút).

```
mỗi 5 phút, GET
  https://salesmate-api-dev.onrender.com/api/health
  https://salesmate-ai-core.onrender.com/health
```

**Hai job riêng, không phải một.** Cron ngoài hồi sinh được service đã ngủ; mọi
cơ chế bên trong thì không.

**TUYỆT ĐỐI không ping `/api/chat`** — mỗi lượt gọi model thật và tốn tiền.

Tạo xong phải **mở lịch sử chạy của từng job và xác nhận có dòng 200**. Lần đầu
làm việc này, job im lặng không chạy và không để lại dấu vết nào trong log Render
— mất hai ngày mới phát hiện.

Kiểm lại sau 20 phút không ai đụng vào web: gọi cả hai URL, **cả hai phải dưới 1
giây**. Trên 30 giây nghĩa là service đó vẫn ngủ.

### Ngân sách 750 giờ — cạn là CHẾT, không phải chậm

750 giờ instance mỗi tháng tính cho **cả workspace**, reset ngày 1. Giữ thức 24/7
hai service tốn ~48 giờ/ngày, tức cạn sau ~15,6 ngày. Cạn thì Render **treo toàn
bộ service free** tới đầu tháng sau.

Kế hoạch đã chốt cho đợt demo:

| Khoảng | Ping | Giờ |
|---|---|---|
| 22–31/08 | 24/7 | 480h + đã dùng |
| 01–15/09 | 24/7 | 720h |
| từ 16/09 | **TẮT cron** | còn ~30h cho lưu lượng tự nhiên |

Xem đồng hồ ở Dashboard → Billing → *Free Instance Hours*.

### Lưới an toàn trong app

Khi khách mở widget chat, **trình duyệt của họ** gọi thẳng `ai-core/health` bằng
`fetch(..., {mode: 'no-cors'})` — xem `danhThucTroLy()` trong
`interface/frontend/src/api/index.js`. Trình duyệt ở ngoài Render nên đánh thức
được thật.

`no-cors` vì ta không cần đọc kết quả, chỉ cần request chạm tới Render. Nhờ vậy
lõi AI không phải khai CORS cho tên miền frontend.

URL lõi AI lấy từ `/api/health` chứ không hardcode — nó khác nhau giữa máy mình
và Render.

Đây là **lưới an toàn**, không thay được cron: nó chỉ chạy khi đã có người mở
web, mà người đầu tiên chính là người phải chờ.

### Điều không chữa được bằng gói free

Ngày 20/08/2026 Render tắt hẳn spin-up của Web Service gói free vì sự cố Google
Cloud. Service nào đang ngủ thì không dậy nổi, ping bao nhiêu cũng vô ích.

Giữ thức liên tục thu hẹp rủi ro này gần bằng 0 — service đang chạy không đi qua
đường spin-up. Nhưng nếu nó lỡ ngủ đúng lúc sự cố xảy ra thì không có gì trong
tay mình cứu được. Muốn loại hẳn thì phải trả tiền: đổi `plan: free` thành
`plan: starter` (~$7/tháng) cho `salesmate-ai-core` trong `render.yaml`.

**Build đầu tiên trên Render lâu** (5–10 phút) vì phải cài `psycopg`. Các lần sau
có cache, nhanh hơn nhiều.

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
| `AI_CORE_API_KEY` | **cả hai service** | phải TRÙNG nhau; lệch là mọi câu hỏi trả 401 |
| `OPENAI_API_KEY` | `salesmate-ai-core` | **bắt buộc** — bỏ trống thì service không khởi động |
| `VITE_API_BASE_URL` | Vercel | Production và Preview cùng giá trị |
