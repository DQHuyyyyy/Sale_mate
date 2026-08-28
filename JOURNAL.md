# Nhật ký phát triển — SalesMate (P-055)

> **Cách đọc file này.** Phần "Hồ sơ giải trình AI" ở cuối là phần quan trọng
> nhất: nó nói đoạn nào do AI sinh, đã kiểm bằng cách nào, và **sửa lại những
> gì**. Phần theo tuần ở trên là bối cảnh.
>
> ⚠️ **File này dựng lại ngày 28/08/2026 từ chứng cứ trong repo** — git log,
> `WORKLOG.md`, `CLAUDE.md`, migration, và các file kết quả trong `eval/results/`
> — chứ không phải viết dần theo tuần. Mọi sự cố nêu dưới đây đều truy được về
> một file hoặc một commit; nhưng ngày tháng là ngày commit, không phải ngày
> nghĩ ra. Ai có ghi chép cá nhân chính xác hơn thì sửa thẳng vào đây.

Đội: **huy** (frontend + tích hợp) · **dat** (data) · **viet** (agent) ·
**phuc** (API).

---

## Tuần 1: 23/07 – 02/08

### Mục tiêu
- [x] Dựng khung bốn module chạy song song mà không chặn nhau
- [x] Pipeline ingest tài liệu vào vector store, chứng minh RAG chạy đầu-cuối
- [x] Thu thập dữ liệu tồn kho và tin rao thật

### Đã hoàn thành
- Khung `src/` với **Protocol + dependency container**: mỗi module chỉ import
  `contracts.py` và `models/` của module khác. Lý do ghi ở
  [ADR-004](docs/adr/ADR-004-module-contracts.md).
- `bootstrap.py` — một file duy nhất gắn Protocol ↔ implementation.
- Pipeline ingest chạy được với Qdrant thật + `OpenAIEmbedder`.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Bốn người sửa chung một cây code, PR đụng nhau liên tục | Cách ly bằng Protocol; `models/` và mọi `contracts.py` **đóng băng**, muốn sửa thì PR riêng | Bốn nhánh cá nhân chạy song song hết dự án |
| Crawl `batdongsan.com.vn` bị Cloudflare chặn (`cf-mitigated: challenge`) | **Không né tránh.** Chuyển sang thu thập thủ công 33 trang rồi viết parser xử lý hàng loạt | 33/33 parse đúng |

### Bài học
- Đóng băng hợp đồng sớm rẻ hơn nhiều so với gỡ rối muộn.
- Gặp tường chống bot thì dừng lại, không tìm cách vượt.

---

## Tuần 2: 03/08 – 09/08

### Mục tiêu
- [x] Gộp API sản phẩm + frontend vào `interface/`
- [x] Đăng nhập, phân quyền, portal tìm kiếm căn
- [x] Nối widget chat vào lõi AI qua `AI_CORE_URL`

### Đã hoàn thành
- Ba service: portal `:8000` · lõi AI `:8001` · frontend `:5173`.
- `interface/backend` chỉ **chặn quyền rồi dẫn ống** sang lõi AI, không parse
  event SSE — nhờ vậy thêm loại event mới không phải sửa nó.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Tên cột thật của `salemate_v1` không khớp bản đặc tả (`"Số đỏ"` chứ không phải "Sổ đỏ"; `"Loại căn\n(PN, WC)"` có ký tự xuống dòng) | Gom hết tên cột vào `app/core/columns.py`, sửa code theo **database**, không theo đặc tả | Không ai gõ tay tên cột ở chỗ khác nữa |
| Cột `"Giá"` là text (`'1,8 tỷ'`) nên không lọc `BETWEEN` được | Thêm cột **sinh tự động** `gia_tri` | Sửa `"Giá"` là cột số tự đổi theo, không bao giờ lệch |

### Bài học
- **Database là nguồn sự thật, đặc tả chỉ là ý định.** Lệch nhau thì sửa đặc tả.

---

## Tuần 3: 10/08 – 16/08

### Mục tiêu
- [x] Tool tồn kho đọc thẳng Postgres, không đi qua RAG
- [x] Trích nguồn bấm vào xem được
- [x] Tool `dat_coc` ghi lead cho đội sale

### Đã hoàn thành
- `inventory_units` thành **VIEW** trên `salemate_v1`
  ([migration 005](interface/backend/migrations/005_inventory_units_view.sql)).
- Trang `/tai-lieu` + `/tai-lieu/{doc_id}` — đích của nút trích nguồn.
- Bảng `dat_coc_lead` + trần `TOI_DA_GIU_MOI_SO = 3`.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Tồn kho từng là **bảng sao chép** của `salemate_v1` và đã trôi lệch **4 căn sai giá** | Đổi thành VIEW — một nguồn sự thật duy nhất | Chatbot và portal luôn nói cùng con số |
| Lead `new` khoá căn mà cọc không tự hết hạn ⇒ một người gửi 100 request là cả kho "hết hàng" | Trần 3 căn/số điện thoại, ở **cả hai** đường ghi lead | Có phanh chống khoá sạch tồn kho |
| Dòng "Nguồn" hiện y hệt một tên tài liệu ba lần | `_bo_trung` khử theo `doc_id`, xếp tài liệu đóng góp nhiều đoạn nhất lên đầu | Một tài liệu một dòng |

### Bài học
- **Hai nơi cùng nắm một sự thật là một lỗi sắp xảy ra**, không phải một tối ưu.
- Luật chép hai bản (hai service tách nhau) thì phải ghi rõ ở cả hai chỗ rằng
  sửa một bên là vô nghĩa.

---

## Tuần 4: 17/08 – 23/08

### Mục tiêu
- [x] Quản lý ảnh căn hộ (bìa, xoá, upload)
- [x] Màn `/giao-dich` — van xả của cơ chế trạng thái căn
- [x] Dọn kho vector

### Đã hoàn thành
- Bucket `apartment-images` tạo **tường minh** (public, 8MB, JPG/PNG/WEBP/GIF).
- Một màn `/giao-dich` cho cả sale lẫn admin, thay ba mục menu cũ.
- Gỡ 871 chunk tin rao khỏi Qdrant; kho còn đúng 11 tài liệu / 39 chunk.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Câu "tìm căn khoảng giá 3 tỷ" trả về **hàng của sàn khác** kèm số điện thoại môi giới khác, trích "Mã tin: 307426397" | Gỡ hẳn ba nguồn tin rao khỏi Qdrant | Không phải thiếu vài căn — là **sai kho**, và đã sửa đúng gốc |
| `ingest` hỏng **0/10 file** suốt một thời gian dài mà không ai biết (thiếu heading H1 khớp `title`) | Sửa file nguồn; đặt luật `doc_id` trong Qdrant **phải** có file nguồn trong repo | Kho nạp lại được, và review được |
| Mọi lần upload ảnh trả 400 "Bucket not found" — project Supabase **không có bucket nào** | Tạo bucket bằng tay, backend cố ý KHÔNG tự tạo | Hạ tầng do người duyệt, không do code lặng lẽ dựng |

### Bài học
- **Hạ tầng code tự dựng là hạ tầng không ai review.** `ensure_table()` đã tạo
  `dat_coc_lead` trên production trước migration 009 — bảng thiếu DEFAULT, thiếu
  CHECK, thiếu unique index, và **thiếu RLS** trên bảng chứa số điện thoại khách
  thật. [Migration 012](interface/backend/migrations/012_dat_coc_lead_va_schema.sql)
  vá lại.
- Tài liệu chỉ tồn tại trong vector store là tài liệu **mất hẳn** nếu collection
  hỏng. `phap-ly-thu-tuc` phải ghép lại từ chunk mới cứu được.

---

## Tuần 5: 24/08 – 28/08

### Mục tiêu
- [x] Cổng phân loại chính sách chặn câu ngoài phạm vi
- [x] Đo lại model trả lời trên golden dataset
- [x] Xử lý 5 issue mentor raise (#24–#28)

### Đã hoàn thành
- `ChinhSachNode` chạy **song song** với `tools`+`retrieve` (17,6s so với 18,3s
  của bản không cổng — nằm trong dao động giữa hai lần chạy).
- Đo `gpt-5.6-luna` trên 29 câu golden: **17 đạt / 2 không đạt**, dòng "Nguồn"
  đầy đủ ở mọi lượt có khẳng định (`eval/results/diem_20260826-1609_batch3-sua.md`).
- Vá 5 issue của mentor — chi tiết ở mục dưới.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Tài khoản Anthropic chạm trần chi tiêu tháng ⇒ cổng chính sách **ngừng bảo vệ hoàn toàn trong im lặng** | Ghi rõ cổng thất bại theo hướng MỞ; dòng WARNING "Cổng chính sách hỏng" là tín hiệu duy nhất | Phát hiện bằng cách hỏi trợ lý làm thơ và được đáp ứng |
| Luật `khi_thieu` của cổng leo thang khớp **0/8** câu điển hình | Đổi mặc định sang `moi_luot`, rồi siết theo số đo | Một tính năng không bao giờ chạy thì không khác gì không có |

### Bài học
- **Chạy rộng trước rồi thu hẹp theo số đo.** Thiết kế hẹp sẵn thì không có dữ
  liệu nào để biết nên nới bao nhiêu.
- Cổng bảo vệ mà **thất bại theo hướng mở** thì hạn mức nhà cung cấp là vấn đề
  an toàn, không phải chuyện kế toán.

### Kế hoạch tiếp
- [ ] Merge `develop` → `main` (đang lệch 21 commit) hoặc đổi nhánh mặc định
- [ ] Nối phân quyền tới tầng truy hồi (xem mục "Nợ kỹ thuật" dưới)
- [ ] Đo cổng leo thang trên bộ eval để có cơ sở xoá `PlanNode`/`ActNode`

---

# Hồ sơ giải trình AI

Dự án dùng AI coding assistant ở **hầu hết** các file. Phần này không liệt kê
"chỗ nào có AI" — gần như chỗ nào cũng có. Nó liệt kê thứ có giá trị hơn:
**những chỗ AI sinh ra sai, sai thế nào, phát hiện bằng cách nào, và sửa thành
gì.** Mỗi mục dưới đây đều truy được về một file trong repo.

## Cách làm việc

| | |
|---|---|
| Công cụ | Claude Code (chính) · Codex · Cursor · Gemini |
| Ghi log | Hook bắt buộc của BTC bắn `.ai-log/*.jsonl` thẳng lên server BTC; repo chỉ giữ phần cơ khí ở `scripts/` (xem [`.agents/rules/ai-log-hook.md`](.agents/rules/ai-log-hook.md)) |
| Chốt chặn | Không PR nào vào `develop` mà chưa qua `make check` + review người |
| Ranh giới | `src/models/` và mọi `contracts.py` **đóng băng** — AI không được sửa trong PR tính năng |

**Ba nguyên tắc nghiệp vụ là thứ AI dễ vi phạm nhất**, nên chúng được viết thành
test chứ không chỉ viết thành lời dặn: không bịa số · luôn trích nguồn · phân
quyền lọc tại tầng truy hồi.

## Những chỗ AI sinh sai và đã sửa lại

### 1. Bịa số liệu tài chính — nặng nhất

**AI sinh:** node `generate` rút tham số chính sách vay **từ văn xuôi** trong
tài liệu.

**Sai thế nào:** hỏi "tôi có 1 tỷ, mua VOP397 thì vay thế nào", model lấy đúng
giá từ tool rồi **tự thêm** "ngân hàng cho vay lên đến 70–80% giá trị". Không
tài liệu nào nói vậy. Đây là con số khách mang đi hỏi ngân hàng.

**Sửa:** tách con số ra khỏi văn xuôi. Tham số định lượng nằm ở
[`tools/data/chinh_sach_vay.json`](src/agents/tools/data/chinh_sach_vay.json) —
trần lãi suất, số tháng khoá, phụ phí, và `hieu_luc_den`. Văn bản vẫn ở Qdrant
để trích dẫn; chỉ con số dùng để **tính** mới ra file JSON, tức là mỗi lần sửa
là một PR có review.

### 2. Bịa số tiền cọc

**AI sinh:** prompt cho phép trợ lý trao đổi về đặt cọc một cách tự nhiên.

**Sai thế nào:** hệ thống **không có dữ liệu nào** về số tiền cọc, thời hạn giữ
chỗ hay mức phạt — nhưng model vẫn nói được, vì đó là kiến thức chung.

**Sửa:** prompt cấm tuyệt đối, và **test khẳng định `data` của tool `dat_coc`
không chứa đơn vị tiền**. Lời dặn trong prompt một mình không đủ.

### 3. Số điện thoại khách chảy vào log nhà cung cấp LLM

**AI sinh:** tool `dat_coc` trả cả thông tin lead về trong `data`.

**Sai thế nào:** `data` đi vào prompt, prompt đi vào log của nhà cung cấp LLM.
Bảng `dat_coc_lead` có RLS; log thì không.

**Sửa:** số điện thoại **không** được trả lại vào `data`. Cùng luật đó áp cho
VIEW `inventory_units` — [migration 010](interface/backend/migrations/010_trang_thai_dat_coc.sql)
chỉ gom hai boolean từ bảng lead, **không kéo cột `ho_ten`/`so_dien_thoai` nào
ra**, vì từng dòng của view đi thẳng vào prompt.

### 4. Trích nguồn dựng lại đúng thứ backend vừa lọc bỏ

**AI sinh:** frontend tự rút dấu `[…]` từ thân bài để dựng dòng "Nguồn".

**Sai thế nào:** đường đó **không đi qua bộ lọc nào**, nên mọi luật ở
`nguon.py` vô hiệu. Đã xảy ra thật: trợ lý hỏi ngược "bạn muốn lọc theo tiêu chí
nào?" mà dưới đó có "Nguồn: VOP758, VOP247, VOP619" — ba căn backend vừa loại.
Thân bài còn cụt thành "…và diện tích **như.**" sau khi FE gỡ dấu.

**Sửa:** backend nói thẳng qua `data.cho_trich_nguon`; FE chỉ nghe theo. Quyết
định nằm ở **một chỗ duy nhất là Python**. Thêm nữa: nhãn model tự viết không
còn được tính là nguồn — model từng chép `[Sang tên Sổ đỏ 2026 — LuatVietnam]`
từ mục "Nguồn tham khảo" cuối tài liệu, làm dòng "Nguồn" trỏ sang một bài báo
ngoài trong khi trợ lý đọc tài liệu nội bộ.

### 5. Lưới an toàn trích nguồn dựng nguồn cho câu không nhắc căn nào

**AI sinh:** lưới an toàn "lượt có dữ liệu tool mà không nguồn nào lọt thì giữ
lại vài cái đầu".

**Sai thế nào:** đo trên production với câu "Căn ở Ocean Park 1" — tool trả 23
căn, trợ lý **hỏi ngược** và chỉ nêu con số 23. Lưới dựng lại VOP758, VOP285,
VOP619 dưới một câu **không nhắc căn nào**. Người đọc bắt được ngay, rồi mất tin
vào cả dòng nguồn ở những lượt đúng.

**Sửa:** tách thành hai phép kiểm khác nhau — `_co_khang_dinh_ve_can` (có gì cần
chứng minh không) và `_khang_dinh_ve_mot_can_cu_the` (có trỏ vào MỘT căn không).
Khác nhau đúng ở chữ "23 căn": là khẳng định thật, nhưng đếm cả tập kết quả.

### 6. Phân quyền lead kiểm vai trò mà không kiểm quyền sở hữu

**AI sinh:** `PATCH /api/dat-coc/{lead_id}` gắn `require_sale_hoac_admin`.

**Sai thế nào:** dependency đó chỉ kiểm **vai trò**. Câu `UPDATE` không có
`AND sale_id = %s`, nên bất kỳ sale nào cũng đổi được trạng thái lead của sale
khác — gồm cả chốt bán — và mệnh đề `RETURNING` trả về luôn tên với số điện
thoại khách của họ. `lead_id` là số nguyên tăng dần nên không phải đoán gì.

**Phát hiện:** mentor, issue #28-series (#24). **Không phải test của đội bắt
được** — đó là điều đáng ghi nhất ở mục này.

**Sửa:** `_dieu_kien_so_huu()` ghép mệnh đề sở hữu **ngay trong câu ghi** (cả
nhánh đổi trạng thái lẫn nhánh chốt bán), 404 không phân biệt "không tồn tại"
với "không thuộc quyền", và 5 test khoá lại. Tập được **ghi** phải trùng đúng
tập được **đọc** ở `danh_sach` — lead của mình cộng lead chưa ai nhận.

### 7. Lõi AI phơi công khai, không xác thực

**AI sinh:** `render.yaml` khai lõi AI là `type: web`; `src/api/v1/chat.py`
không có `Depends` nào.

**Sai thế nào:** Render cấp URL công khai. Ai biết URL đều gọi thẳng
`/api/v1/chat` được, bỏ qua toàn bộ hạn mức và phân quyền của API sản phẩm — mà
lõi AI mới là chỗ tốn tiền model. `/api/v1/documents` thì để hở cả hồ sơ nội bộ.

**Phát hiện:** mentor (#25).

**Sửa:** [`src/api/bao_ve.py`](src/api/bao_ve.py) — khoá dịch vụ dùng chung
(`X-API-Key`, so bằng `compare_digest`) + phanh chi phí theo tiến trình. Thiếu
khoá trên `production` thì **chặn hết**, không cho qua: cổng thất bại theo hướng
mở thì không phải cổng.

### 8. Thẻ chống prompt injection tự vô hiệu hoá được

**AI sinh:** `<ngu_canh>` bọc tài liệu, kèm chú thích nói rõ đây là biện pháp
chống prompt injection.

**Sai thế nào:** nội dung bên trong **không được escape**. Một tài liệu chứa
chuỗi `</ngu_canh>` đóng sớm vùng dữ liệu, và phần sau đó model đọc như chỉ thị
hệ thống. Biện pháp chống injection bị vô hiệu bằng mười ký tự.

**Phát hiện:** mentor (#27).

**Sửa:** `_vo_hieu_the_dong()` bẻ mọi biến thể thẻ đóng (kể cả `</ ngu_canh >`),
thay bằng ký tự lookalike để không mất nội dung tài liệu; **và** thêm luật vào
system prompt. Hai vế phải đi cùng nhau — một câu luật mà vùng dữ liệu vẫn thoát
ra được thì luật đó nói về một vùng không tồn tại.

### 9. Tài liệu AI sinh mô tả sai chính code mình vừa viết

**AI sinh:** `README.md` viết "chưa có `OPENAI_API_KEY` thì lõi AI **vẫn chạy**:
tự rơi về LLM giả lập".

**Sai thế nào:** đường rơi về giả lập **đã bị bỏ** ở `bootstrap.py` — thiếu khoá
là `ConfigurationError` ngay lúc khởi động. README không được cập nhật theo.
Người mới đọc README sẽ đi tìm nguyên nhân ở chỗ khác.

**Phát hiện:** mentor (#26).

**Sửa:** README nói đúng hành vi, kèm **cách chạy được gì khi chưa có khoá**.
Cùng đợt: sửa số test 240→753 và coverage 77%→76%, đo lại bằng `make cov` chứ
không chép lại con số cũ.

### 10. Vòng lặp agent bịa tên tool và tự lặp vô hạn

**AI sinh:** `PlanNode` để model tự chọn hành động tiếp theo.

**Sai thế nào:** model bịa tên tool không có thật; xin đi xin lại cùng một hành
động; điền `""` cho trường không dùng (`{"unit_code": "VOP397", "building": ""}`
dịch thành `ILIKE ''` nên không khớp gì, agent tưởng thiếu dữ liệu rồi lặp cho
hết trần); và hỏi ngược người dùng khi **chưa tra cứu lần nào**.

**Sửa:** năm chốt chặn, mỗi chốt một chỗ, ghi rõ trong CLAUDE.md là **không được
gỡ khi thêm tính năng**. Bốn chốt đầu chặn agent làm quá nhiều; chốt cuối chặn
nó làm quá ít.

### 11. Trợ lý kể cho khách nghe về ngữ cảnh của chính nó

**AI sinh:** `ghi_chu` viết `` `can_hien_thi` chỉ là 30 căn đầu ``.

**Sai thế nào:** ghi chú đó viết cho **model** đọc, nhưng model tưởng là thông
tin phải truyền đạt và nói lại nguyên văn với khách: *"hiện ngữ cảnh cung cấp
chi tiết 30 căn đầu…"*. Vô nghĩa với người mua nhà, và nghe như hệ thống đang
giấu 13 căn.

**Sửa:** `_ghi_chu_cat_bot()` chỉ nêu con số tổng và cấm tường minh việc kể lại
cơ chế. Có test khoá cả hai vế.

## Nợ kỹ thuật đã biết — ghi lại trước khi quên

| Nợ | Ở đâu | Vì sao chưa trả |
|---|---|---|
| **Phân quyền chưa nối tới tầng truy hồi** — `RetrieveNode` ghim cứng `["public"]` | `src/agents/graph.py` (`build_nodes`) | `ChatRequest` không mang danh tính người dùng, mà `src/models/` đóng băng ⇒ cần PR contract riêng. Hôm nay vô hại vì cả 11 tài liệu đều `public`; `test_moi_tai_lieu_deu_public_cho_toi_khi_noi_duoc_quyen` canh cho điều đó không lặng lẽ hết đúng |
| `PlanNode`/`ActNode` và `ENABLE_AGENT_LOOP` còn nguyên dù orchestrator đã thay | `src/agents/nodes/` | Orchestrator **chưa được đo trên bộ eval** nên chưa có cơ sở để xoá. Không bật cả hai cờ cùng lúc |
| `system_v7.md` tồn tại nhưng `SYSTEM_PROMPT_VERSION = "v6"` | `src/agents/prompts/__init__.py` | Đổi prompt phải **đo trước** bằng `cli eval answer --compare v6 v7`. Luật chống injection vì thế thêm vào **cả hai** bản |
| Trần lượt của khách khoá theo IP, sau proxy Render có thể gộp mọi khách một rổ | `app/core/han_muc.py` | Sửa đúng chỗ là cấu hình `--forwarded-allow-ips` của uvicorn, không phải đọc tay `X-Forwarded-For` |
| Một Supabase project dùng chung cho mọi môi trường | `DEPLOY.md` | Sửa dữ liệu khi test là người dùng thấy ngay, và migration chạy thẳng lên production |

## Bài học lớn nhất

**AI sinh code chạy được rất nhanh, nhưng nó không biết cái giá của một sai
sót.** Bốn mục đầu (§1–§4) đều là code *chạy đúng* — không exception nào, không
test nào đỏ — mà nội dung thì sai theo cách chỉ có người đọc mới bắt được: một
con số lãi suất không có trong tài liệu nào, một dòng "Nguồn" liệt kê ba căn
không được nhắc tới.

Nên chốt chặn hiệu quả nhất trong dự án này không phải review từng dòng, mà là
**biến từng nguyên tắc nghiệp vụ thành một test đỏ được**, rồi ghi vào
`CLAUDE.md` *vì sao* nó tồn tại. Nguyên tắc chỉ nằm trong lời dặn thì lần sinh
code sau sẽ bỏ qua nó.

Và §6–§9 nói một điều khó chịu hơn: **bốn lỗ hổng do mentor tìm ra, không phải
đội.** Ba trong số đó là bảo mật. Điểm chung là chúng đều nằm ở chỗ *thiếu* một
thứ — thiếu một mệnh đề `WHERE`, thiếu một `Depends`, thiếu một lệnh escape — mà
test thì viết theo thứ *có*. Bài học: với logic bảo mật, phải viết test cho **ca
bị từ chối** trước ca thành công.
