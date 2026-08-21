# CLAUDE.md — SalesMate (P-055)

> Điểm vào cho AI coding assistant và cho thành viên mới. Đọc file này trước.

## Sản phẩm

**Portal bất động sản xác thực** (kiểu Meey Land) + **trợ lý AI dạng widget nổi**
góc dưới phải. Không phải app nội bộ cho sale — đó là bản thiết kế cũ, đã đổi.

Đặc tả đầy đủ trong [`Context Product/`](Context%20Product/):

| File | Nội dung | Trạng thái |
|---|---|---|
| `Giaodien.md` | Design token, cấu trúc trang, component, widget AI | ✅ hiện hành |
| `Core.md` | Lõi agent | ⚠️ đang thiết kế lại, mô tả sản phẩm cũ |
| `Data.md` · `API.md` · `Kientruc.md` | Schema, hợp đồng API, kiến trúc | ⚠️ mô tả sản phẩm cũ |

Khi `Core.md` chưa cập nhật, **đừng suy ra hành vi agent từ nó**. Khung code đã
dựng sẵn chỗ cắm (HITL, phân quyền, trích nguồn) nhưng chưa bật.

## Ba nguyên tắc không được vi phạm

1. **Không bịa số.** Giá, diện tích, tình trạng căn chỉ nêu khi có trong tài liệu
   hoặc kết quả tool.
2. **Luôn trích nguồn** cho khẳng định lấy từ tài liệu.
3. **Phân quyền lọc tại tầng truy hồi**, không lọc ở UI.

## Kiến trúc — điều quan trọng nhất cần nắm

Bốn người làm song song. Cách ly bằng **Protocol + dependency container**:

```
src/
├── core/         config · logging · exceptions · container    dùng chung
├── models/       DTO — HỢP ĐỒNG FE ↔ BE                       🔒 ĐÓNG BĂNG
├── data/         contracts.py + ingestion/ stores/ retrieval/  → dat
├── agents/       contracts.py + graph · nodes/ · tools/        → viet
├── api/          deps · errors · v1/                           → phuc
├── services/     adapter ra ngoài: llm.py
├── bootstrap.py  🔑 NƠI DUY NHẤT gắn Protocol ↔ implementation
└── main.py
interface/        FE + API sản phẩm, gộp một chỗ cho dễ quản lý
├── frontend/     Vite + React (JavaScript) — portal + widget    → huy
└── backend/      API sản phẩm :8000, gọi lõi AI qua AI_CORE_URL
```

**Quy tắc bắt buộc:**

- Module chỉ import `contracts.py` và `models/` của module khác.
  **Không bao giờ** import class cụ thể (`QdrantVectorStore`, `OpenAIProvider`…).
- `src/models/` và mọi `contracts.py` **đóng băng**. Muốn sửa → PR riêng vào
  `develop`, cả team review, không lẫn vào PR tính năng.
- Sửa `src/models/` thì phải kiểm luôn phía FE đọc nó ở
  `interface/frontend/src/api/client.js` — frontend là JavaScript thuần, không
  có file type riêng để đồng bộ.

Lý do: [ADR-004](docs/adr/ADR-004-module-contracts.md).

📖 Kiến trúc lõi AI đầy đủ — node, cổng leo thang, phân bổ model kèm
chi phí đo thật, và danh sách bẫy đã gặp:
[docs/kien-truc-loi-ai.md](docs/kien-truc-loi-ai.md).

### Cần thêm trường hoặc loại event mới?

**Dùng `ChatEvent.data` trước.** Nó là `dict[str, Any]` tự do, thêm gì cũng
không đụng hợp đồng. Chỉ mở PR contract khi `data` thật sự không diễn đạt nổi.

Ví dụ đang chạy: sự kiện tiến trình của agent (router → tools → retrieve) đều
phát dưới nhãn `ROUTE` có sẵn, chi tiết nằm ở `data.step`. `ChatEventType` khai
sẵn `ROUTE` · `SOURCES` · `SENSITIVE` chính là để mở rộng kiểu này mà không phải
sửa hợp đồng — đọc docstring của nó.

## Cắm implementation ở đâu

Mở [`src/bootstrap.py`](src/bootstrap.py) — một file, đọc là biết hệ thống đang
chạy bằng gì. Hiện tại:

| Protocol | Đang chạy | Ghi chú |
|---|---|---|
| `LLMProvider` | `OpenAIProvider`, rơi về `ScriptedProvider` khi thiếu key | |
| `Embedder` | `OpenAIEmbedder` / `FakeEmbedder` khi thiếu key | BGE-M3 sau — [ADR-002](docs/adr/ADR-002-embedding-tieng-viet.md) |
| `VectorStore` | **`QdrantVectorStore`** (Cloud) · in-memory khi `APP_ENV=test` | |
| `Reranker` | `KeywordOverlapReranker` | `cross_encoder` cần torch ~2GB |
| `Retriever` | **`DefaultRetriever`** — RAG đang BẬT | |
| `AgentService` | `LangGraphAgentService` | |
| `ToolCallingProvider` | `AnthropicToolProvider` · `ScriptedToolCallingProvider` khi tắt cờ hoặc thiếu key | chỉ dùng ở nhánh leo thang |

**Hai nhà cung cấp, hai mức độ thiết yếu.** Thiếu `OPENAI_API_KEY` là **dừng
khởi động** — nó nằm trên đường đi chung, thiếu là trợ lý câm. Thiếu
`ANTHROPIC_API_KEY` (hoặc thiếu cả gói `anthropic`) thì **app vẫn chạy đủ chức
năng**, chỉ tắt nhánh leo thang. `make_tool_provider` bọc try/except quanh cả
việc *dựng* provider chứ không chỉ việc gọi: đã có lần thiếu gói làm
`AgentService` không resolve được và **mọi** request trả 502.

Mọi lựa chọn lấy từ `Settings`, **không hardcode** — đổi hành vi bằng biến môi
trường (`ENABLE_RAG`, `RERANKER`, `QDRANT_URL`), không phải sửa code rồi commit.

Test luôn dùng vector store trong bộ nhớ: không test nào được gọi Qdrant thật.

## Dữ liệu RAG

Một dòng lệnh duy nhất cho mọi thao tác dữ liệu:

```bash
python -m src.cli status            # vector store đang có gì
python -m src.cli ingest --all      # nạp mọi nguồn
python -m src.cli search "câu hỏi"  # thử truy hồi
python -m src.cli eval retrieval    # đo tầng truy hồi
python -m src.cli eval answer --compare v6 v7      # đo PROMPT, chạy cả hai bản
python -m src.cli eval answer --label baseline     # đo MODEL, ghi ra file có nhãn
python -m src.cli eval answer --doi-chieu a b      # so hai file đã ghi, không gọi model
```

**Đổi prompt dùng `--compare`, đổi model dùng `--label` + `--doi-chieu`.**
`--compare` chạy hai bản trong cùng một tiến trình, mà model lấy từ `Settings`
— một tiến trình chỉ có một cấu hình. Trước đây tên file kết quả khoá theo
phiên bản prompt, nên hai lần chạy khác model trên cùng v7 ghi đè lên nhau.

**Hai bài đo, đừng lẫn.** `eval retrieval` đo embed → search → rerank và **không
gọi LLM**, nên đổi prompt xong chạy nó thì con số không nhúc nhích. `eval answer`
mới đo thứ prompt quyết định: cầm tài liệu rồi thì trả lời hay từ chối. Bộ câu
hỏi của nó ([`eval/answer_dataset.json`](eval/answer_dataset.json)) cố ý **không
có happy case** — mỗi câu là một cái bẫy, và bẫy theo hai hướng ngược nhau:
`phai_tra_loi` bẫy từ chối oan, `phai_tu_choi` bẫy bịa. Nhóm `phai_tu_choi` là
cột phanh: nới prompt mà làm nó giảm là đổi lỗi nhẹ lấy lỗi nặng.

Chấm bằng luật tất định, không dùng LLM làm giám khảo. Bộ chấm dùng lại
`la_loi_tu_choi()` của [`src/agents/nguon.py`](src/agents/nguon.py) — chính hàm
đang chạy thật lúc runtime — nên eval và sản phẩm hiểu "từ chối" giống hệt nhau.

Thêm nguồn mới: viết hàm `ingest_<tên>()` trong `src/data/ingest.py` rồi thêm
một dòng vào `SOURCES` cuối file đó. **Không tạo script rời** — bài học cũ: bốn
script tự dựng `QdrantVectorStore` riêng nên chạy tốt, trong khi `bootstrap.py`
vẫn dùng in-memory, web app đứt khỏi dữ liệu nhiều ngày mà không ai phát hiện.

**Dữ liệu tồn kho KHÔNG đi đường này.** Giá và tình trạng căn nằm ở Postgres,
tool đọc trực tiếp — xem mục "Thêm một tool". `inventory_units` là VIEW trên
`salemate_v1` ([migration 005](interface/backend/migrations/005_inventory_units_view.sql)),
nên chatbot và portal luôn nói cùng một con số. Trước đó nó là bảng sao chép và
đã trôi lệch 4 căn sai giá.

### Qdrant chỉ chứa `doc_kind="policy"` — 11 tài liệu, 39 chunk

`SOURCES` giờ chỉ còn `knowledge`, và Qdrant khớp **một-đối-một** với
`data/raw/knowledge/`: mỗi file một `doc_id = knowledge:{tên file}`.

Ba nguồn tin rao đã bị gỡ và 871 chunk của chúng đã xoá khỏi Qdrant:

| Nguồn cũ | Chunk | Vì sao bỏ |
|---|---|---|
| `meeyland` | 695 | tin rao của **môi giới khác**, kèm giá họ niêm yết và số điện thoại của họ |
| `batdongsan` | 76 | như trên |
| `inventory` | 100 | **nhân bản** tồn kho Postgres — đúng hai nguồn số liệu mà mục trên vừa cấm |

Hai nguồn đầu gây một lỗi đã xảy ra thật: câu "tìm các căn khoảng giá 3 tỷ" không
rút được tiêu chí nên tool tồn kho không chạy, truy hồi rơi xuống 864 chunk tin
rao, và trợ lý giới thiệu **hàng của sàn khác cho khách của mình**, trích "Mã tin:
307426397". Không phải thiếu vài căn — là sai kho.

Cần tham khảo mặt bằng giá thị trường thì nạp vào **collection riêng**, đừng để
chung chỗ trợ lý tra tồn kho.

**Dọn ngày 19/08/2026 — ba thứ đã sửa:**

- **100 chunk `inventory:` vẫn còn** dù tài liệu ghi đã xoá. Chúng KHÔNG chứa
  giá lẫn tình trạng (người viết đã cố ý loại), và đều `visibility=internal` nên
  không bao giờ lọt vào truy hồi công khai — rác chết, không phải rủi ro sống.
  Xoá vì đo được: bật `internal` lên thì chúng chiếm **5/5** vị trí, và độ chính
  xác chỉ **1/4** ("hướng Đông Bắc" khớp cả căn Đông Nam, kết quả đầu bảng là
  căn đã bán). Vector khớp ngữ nghĩa gần đúng; lọc thuộc tính rời rạc là việc
  của `WHERE`.
- **21 tài liệu thừa**: 10 bản không dấu từ đợt ingest cũ (file đã không còn) và
  11 tài liệu mồ côi không có file nguồn ở đâu cả.
- **`ingest` hỏng 0/10 file** — mọi file thiếu heading H1 khớp `title`, mà
  `load_knowledge_file` bắt buộc có. Nghĩa là kho không nạp lại được suốt một
  thời gian dài mà không ai biết.

Bài học: **`doc_id` trong Qdrant phải luôn có file nguồn trong repo.** Tài liệu
chỉ tồn tại trong vector store là tài liệu không ai review được, không nạp lại
được, và mất hẳn nếu collection hỏng. `phap-ly-thu-tuc` từng như vậy — phải ghép
lại từ chunk mới cứu được.

### Trang tài liệu — để trích nguồn bấm vào kiểm được

Trích nguồn chỉ có giá trị khi mở ra xem được. `/tai-lieu` liệt kê 11 tài liệu,
`/tai-lieu/{doc_id}` hiện toàn văn — **phải đăng nhập**, vì đó là hồ sơ nội bộ.

Đường đi: FE → `/api/tai-lieu` (portal backend, chặn quyền) → `/api/v1/documents`
(lõi AI) → `load_knowledge_dir()`. Portal backend chỉ chặn quyền rồi dẫn ống,
cùng khuôn với `/api/chat`.

**Đọc từ FILE chứ không từ Qdrant** vì `VectorStore` Protocol không có hàm liệt
kê tài liệu và `data/contracts.py` đóng băng. Đánh đổi: sửa file mà quên `ingest`
thì trang hiện bản mới trong khi trợ lý đọc bản cũ — nên response luôn kèm
`version` để chênh lệch đó nhìn thấy được.

## Phân bổ model — ba vai, hai nhà cung cấp

| Vai | Model | Giá $/1M vào–ra | Ghi chú |
|---|---|---|---|
| router (nhãn + giải tham chiếu), gợi ý | `gpt-5.6-luna` | 0.20 – 1.20 | **rẻ hơn** `gpt-4o-mini` trước đó |
| sinh câu trả lời | `gpt-4o` | 2.50 – 10.00 | chưa đổi, xem bên dưới |
| orchestrator (nhánh leo thang) | `claude-sonnet-5` | 2.00 – 10.00 | giá ưu đãi, hết **31/08/2026** rồi về 3–15 |

Bảng giá nằm ở [`src/core/gia_model.py`](src/core/gia_model.py), mỗi mục có cờ
`da_xac_minh` — mục chưa xác minh vẫn tính được nhưng ghi WARNING, để không ai
lỡ báo cáo một con số tự tin mà sai.

**Vì sao `LLM_MODEL_ANSWER` vẫn là `gpt-4o`:** đây là khâu DUY NHẤT từng có hồi
quy thật khi đổi sang model rẻ — `gpt-4o-mini` bỏ qua luật trích nguồn trên
production trong khi `gpt-4o` ở local thì tuân. Muốn đổi thì **đo trước** bằng
`eval answer --doi-chieu`, và chỉ đổi khi `phai_tu_choi` không giảm.

**Sonnet 5 có ba ràng buộc riêng**, sai là 400 hoặc đội tiền:
`temperature` bị **từ chối** (nên router phải ở lại OpenAI — chỗ đó cần
`temperature=0.0`); `budget_tokens` đã bị gỡ; adaptive thinking bật mặc định và
token suy nghĩ tính theo **giá đầu ra**, nên `ORCHESTRATOR_EFFORT` (mặc định
`low`) là cần ga chi phí chính. Đừng tắt hẳn thinking để tiết kiệm — tắt xong
model gọi tool ít hẳn, đúng thứ orchestrator cần.

## Giải tham chiếu bằng lịch sử

Router trả thêm `entities` — tiêu chí ĐÃ giải tham chiếu từ lịch sử hội thoại
([`src/agents/thuc_the.py`](src/agents/thuc_the.py)). Nhờ vậy "liệt kê 20 căn
đó" chạy được, trong khi trước đây `build_args` chỉ đọc **câu hiện tại** nên
không tool nào nhận.

**Chỉ kế thừa DANH TỪ, không kế thừa ĐỘNG TỪ.** Mã căn, phân khu, khoảng giá,
vốn tự có — thứ hội thoại đang nói *đến* — kế thừa được. Ý định vay, ý định đặt
cọc, dấu hiệu hỏi tổng hợp thì **luôn đọc câu hiện tại**: khách nói "đặt cọc
VOP397" ở lượt 1, lượt 3 hỏi "căn đó hướng nào" mà kế thừa ý định thì `dat_coc`
ghi thêm một lead nữa.

Hai tính chất giữ cho thay đổi này an toàn:

- **Không có lịch sử thì không gọi model.** Lượt đầu vốn không có gì để giải
  tham chiếu, nên bỏ hẳn bước — đường một-lượt chạy y hệt trước đây và mọi con
  số đo cũ vẫn so sánh được.
- **`entities` rỗng thì mọi builder rơi về regex như cũ.** Đường lùi nằm sẵn
  trong thiết kế, không cần revert code.

`ArgBuilder` nhận thêm tham số thứ hai nhưng nó **tuỳ chọn**: registry đọc chữ
ký một lần lúc đăng ký và tự thích ứng, nên tool chỉ cần câu hiện tại vẫn khai
`build_args(query)` như cũ.

## Cổng leo thang — khi nào gọi orchestrator

Bật bằng `ENABLE_ORCHESTRATOR`. Nguyên tắc:
**quyết định SAU khi có bằng chứng, không đoán TRƯỚC.**

Cách hay gặp là để router đoán trước độ khó rồi rẽ nhánh rẻ / nhánh đắt. Vấn đề
không ở việc có nhiều nhánh mà ở *thời điểm* quyết: đoán sai vào nhánh rẻ thì
tool không chạy và câu trả lời tệ đi **không có dấu hiệu nào** — đúng cái ngõ
cụt mà `_KHONG_TRA_CUU` vừa gỡ. Nên cổng chạy sau `tools` và `retrieve`, đọc
state đã gom. Đoán sai luật thì chỉ tốn vài xu, không mất chất lượng.

`CHE_DO_LEO_THANG` chọn một trong ba:

| Chế độ | Sonnet 5 chạy khi |
|---|---|
| `tat` | không bao giờ |
| `khi_thieu` | một trong ba luật hẹp dưới đây khớp |
| `moi_luot` *(mặc định)* | **mọi câu cần tra cứu** — câu xã giao vẫn bỏ qua |

**Vì sao mặc định là `moi_luot`.** Bản đầu chỉ có `khi_thieu` và đo trên máy
thật thì nó khớp **0/8** câu điển hình: R1 đòi độ phủ dưới ngưỡng mà
`KeywordOverlapReranker` cho điểm rộng tay (0,468–0,888 cả với đoạn không liên
quan), còn R2/R3 đọc thực thể vốn rỗng ở câu một lượt. Một tính năng không bao
giờ chạy thì không khác gì không có — và dấu hiệu duy nhất là hoá đơn Anthropic
bằng 0.

Bài học: **chạy rộng trước rồi thu hẹp theo số đo.** Hẹp sẵn thì không có dữ
liệu nào để biết nên nới bao nhiêu; rộng thì phanh ngân sách và log nói ngay.

### Ba luật của `khi_thieu`

| Luật | Khớp khi | Chữa ca |
|---|---|---|
| `R1` *(bật)* | cần tra cứu mà bằng chứng KHÔNG ĐỦ — **đúng phép kiểm của `GuardrailNode._has_enough_context`** | đúng nhánh hôm nay trả "chưa đủ dữ liệu" |
| `R2` *(tắt)* | có cả tiêu chí căn lẫn tham số tài chính | chuỗi tool phụ thuộc: tìm căn rồi mới tính vay theo giá căn đó |
| `R3` *(tắt)* | ≥2 mã căn mà `so_sanh_can` không chạy | "so sánh VOP345 với VOP397, căn nào vay lợi hơn" |

Mỗi luật một cờ riêng (`LEO_THANG_R1/R2/R3`) để tắt được độc lập — bật cả ba
cùng lúc thì lúc chi phí vọt lên không biết luật nào gây ra.

R1 phải dùng **đúng** phép kiểm của guardrail, không được tự nghĩ ra phép kiểm
riêng. Bản đầu viết là "`chunks` rỗng" và gần như không bao giờ khớp: truy hồi
luôn trả top-N bất kể có liên quan hay không, nên thứ quyết định từ chối là ĐỘ
PHỦ. Hai bên hiểu "đủ dữ liệu" khác nhau là cách chắc chắn nhất để cổng vô dụng.

**Phanh ngân sách.** `ORCHESTRATOR_DAILY_BUDGET_USD` (0 = không giới hạn) đếm
trong bộ nhớ tiến trình qua [`src/core/chi_phi.py`](src/core/chi_phi.py). Chạm
trần thì cổng tự đóng và khách **vẫn nhận câu trả lời** từ đường tất định, không
phải một thông báo lỗi.

Đo thật ở chế độ `moi_luot`: **$0,0027 – $0,0049 mỗi lượt** khi cache ấm,
$0,0131 ở lượt phải ghi cache. Spec của 6 tool chiếm ~8.400 trong ~10.200 token
đầu vào nên prompt caching là thứ quyết định con số này — xem bẫy "cache ghi mọi
lượt" ở [`docs/kien-truc-loi-ai.md`](docs/kien-truc-loi-ai.md).

`OrchestratorNode` tự gác cổng bên trong thay vì dùng cạnh điều kiện: để ngoài
thì `build_graph` phải nhận `Settings` chỉ để đọc ba cờ, và đường stream lại
phải chép lại cùng logic — đúng kiểu trôi lệch mà `CONTEXT_NODES` sinh ra để
tránh. Node cũng **không bao giờ raise**: lỗi nhà cung cấp đều nuốt và đi tiếp
sang `generate` với bằng chứng đã gom.

⚠️ `PlanNode`/`ActNode` và `ENABLE_AGENT_LOOP` **vẫn còn** — orchestrator chưa
được đo trên bộ eval nên chưa có cơ sở để xoá. Không bật cả hai cờ cùng lúc:
`build_graph` ưu tiên vòng lặp cũ và orchestrator sẽ không có cạnh nào dẫn tới.

## Luồng agent

Hai chế độ, chọn bằng `ENABLE_AGENT_LOOP`.

**Tắt (mặc định) — pipeline tất định:**

```
START → router → tools ─┬─(cần tài liệu)→ retrieve → generate → guardrail → END
                        └─(không cần)──────────────→ generate → guardrail → END
```

**Bật — vòng lặp agent:**

```
START → router → tools ─┬→ retrieve ─┐
                        └────────────┴→ plan ─┬→ act ──────┐ (quay lại plan)
                                              ├→ retrieve ─┤
                                              └→ generate → guardrail → END
```

`plan` vừa quan sát vừa quyết định — nó chạy lại sau mỗi hành động và nhìn toàn
bộ bằng chứng đã gom, nên không cần node `observe` riêng cho cùng một việc.

- `router` — luật từ khoá trước, model rẻ sau. Nhãn lạ thì fallback `general`.
  `needs_retrieval` khai theo **loại trừ** (`_KHONG_TRA_CUU`), không liệt kê
  nhãn được phép: thêm nhãn mới là tự động được tra cứu. Cách cũ liệt kê thuận
  biến `general` thành ngõ cụt — xem chốt thứ năm bên dưới.
- `tools` — chạy tool khai là phục vụ nhãn hiện tại. Nằm trên đường đi chung và
  tự thoát khi không có tool nào nhận, nên thêm tool không phải sửa `graph.py`.
- `retrieve` — chỉ gọi `Retriever` Protocol, không biết gì về Qdrant. Bó vào
  `doc_kind="policy"` khi nhãn là `LEGAL`/`DOCUMENT` **hoặc khi tool đã có dữ
  liệu**: lúc đó số liệu về căn đã lấy từ Postgres rồi, việc còn lại của truy
  hồi là tìm *quy tắc*, không phải gom thêm tin rao.
- `generate` — model mạnh; có context thì ép grounding. Số liệu tool đứng
  **trước** tài liệu trong prompt: tool đọc nguồn sự thật lúc hỏi, vector store
  chỉ là bản chụp.
- `guardrail` — độ phủ thấp → trả "chưa đủ dữ liệu"; gắn cờ nhạy cảm; gộp nguồn
  tài liệu với nguồn tool. Có kết quả tool thì **không** từ chối dù độ phủ 0.

- `plan` *(chỉ khi bật vòng lặp)* — model chọn một trong bốn: `act` gọi thêm
  tool · `retrieve` đi tra tài liệu · `clarify` hỏi ngược người dùng · `answer`
  đã đủ. Khi `clarify` nó kèm vài phương án bấm được ở `plan_options`, gửi ra
  FE qua `data.options` của event `done`. Phương án lấy thẳng **tên tài liệu đã
  truy hồi**, không để model tự nghĩ — model từng chào "ưu đãi Ocean Park 1"
  trong khi kho chỉ có OP2 và OP3, người dùng bấm vào là mất thêm một lượt.
- `act` *(chỉ khi bật vòng lặp)* — chạy tool plan chọn, cộng dồn bằng chứng.

Thêm node: kế thừa `BaseNode`, chỉ viết `execute()` — try/except, log, đo thời
gian đã có sẵn ở lớp cha. Node **không** trả khoá `metadata`, lớp cha đang dùng
khoá đó để gắn thời gian chạy.

### Năm chốt chặn của vòng lặp

Không có chúng thì agent đốt quota hoặc bịa. Đừng gỡ cái nào khi thêm tính năng:

| Chốt | Ở đâu | Chặn chuyện gì |
|---|---|---|
| Trần `agent_max_iterations` | `PlanNode` | model đòi gọi tool mãi |
| Tool phải có trong registry | `PlanNode` | model bịa tên tool |
| Không lặp lại hành động đã thử | `PlanNode` + `da_thu` | agent kẹt, xin đi xin lại một thứ |
| Làm sạch tham số rỗng | `ActNode._lam_sach` | model điền `""` cho trường không dùng |
| Không hỏi ngược khi chưa tra cứu | `PlanNode._phai_tra_cuu_truoc` | agent bỏ cuộc quá sớm |

Bốn chốt đầu chặn agent làm **quá nhiều**; chốt cuối chặn nó làm **quá ít**.
"Ocean park có ưu đãi gì" từng bị router xếp `general` nên không truy hồi gì,
`plan` nhìn state rỗng rồi hỏi ngược "loại ưu đãi nào?" — bịa ra trục mơ hồ,
trong khi trục thật là Ocean Park 2 hay 3 và truy hồi cho độ phủ 0.919 với đúng
hai tài liệu đó. Hỏi ngược mà chưa có bằng chứng là đoán mò chỗ cần làm rõ.

`da_truy_hoi` (do `RetrieveNode` bật) phân biệt "tìm rồi mà không có" với "chưa
hề tìm" — chỉ nhìn `chunks` rỗng thì plan sẽ đòi truy hồi mãi.

Chốt cuối tưởng vặt nhưng đã gây lỗi thật: model trả
`{"unit_code": "VOP397", "building": ""}`, tool dịch `""` thành `ILIKE ''` nên
không khớp gì, agent tưởng thiếu dữ liệu rồi lặp cho hết trần.

Cũng **cố ý không có** đường tắt "tool tất định đã chạy ⇒ trả lời luôn". Từng
có, và nó giết chính vòng lặp: "so sánh VOP345 và VOP397" thì `ToolsNode` chỉ
bắt được mã đầu, plan thấy đã có dữ liệu nên dừng — trả lời một căn rồi im.

## Thêm một tool

Ba việc, không đụng `graph.py` lẫn `nodes/`:

1. Tạo file trong `src/agents/tools/`, class kế thừa `AgentTool`.
2. Gắn `@register_tool(intents={...}, build_args=...)`.
3. Thêm một dòng import vào `tools/__init__.py`.

Hai tầng lọc quyết định khi nào tool chạy:

| | Lọc gì | Chi phí |
|---|---|---|
| `intents` | thô, theo nhãn router | không tốn gì |
| `build_args(query)` | tinh — trả `None` là tool không chạy | không tốn gì |

Nhờ tầng hai mà `intents` khai rộng vẫn an toàn: "tìm căn 2 phòng ngủ" và "căn
VOP345 còn không" cùng nhãn `listing`, nhưng chỉ câu sau rút được mã căn.

**Tool cùng nhãn phải tự nhường nhau ở `build_args`.** Ba tool tồn kho chia việc
theo SỐ mã căn trong câu:

| Số mã căn | Tool chạy |
|---|---|
| 0 | `inventory_search` / `inventory_summary` |
| 1 | `inventory_lookup` |
| ≥2 | `so_sanh_can` |

### Ba trạng thái căn

| `status` | Nhãn | Khi nào |
|---|---|---|
| `available` | Còn | không lead nào đang hoạt động |
| `reserved` | Đã đặt cọc | có lead khác `bo` |
| `sold` | Đã bán | `"Tình trạng (Còn/Hết)" ≠ 'Còn'` |

Cột `trang_thai` của bảng lead giữ năm giá trị (`new`/`da_goi`/`da_coc`/`bo`/
`da_ban`). Mức độ chín của lead là việc **nội bộ đội sale**, không phải trạng
thái căn — với người mua thì `new`/`da_goi`/`da_coc` đều là một điều duy nhất:
"căn này có người rồi".

**`da_ban` là trạng thái cuối, và nó làm ba việc trong một transaction**
([migration 013](interface/backend/migrations/013_lead_da_ban.sql)): ghi
`sales_history` lấy tên + số điện thoại từ chính lead, khoá căn
(`"Tình trạng (Còn/Hết)" = 'Hết'`), rồi đánh dấu lead. Căn khoá bằng `FOR UPDATE`
nên hai người bấm cùng lúc chỉ một người thành công.

Bắt sale gõ lại tên khách ở trang căn hộ là thừa việc, và gõ sai thì
`sales_history` mang tên một người khác với người thật sự mua — không gì đối
chiếu được. Dòng lead **ở lại** sau khi bán: đó là lịch sử của một giao dịch có
thật, xoá đi thì không truy được khách đến từ đâu.

Giá ghi theo **giá niêm yết**. Không có ô nhập giá thương lượng — nếu cần, đó
là một PR riêng thêm ô vào màn Giao dịch, đừng dựng lại đường bán thứ hai.

**Chỉ có MỘT đường ghi nhận bán.** `POST /api/sales` đã bị gỡ cùng nút "Ghi nhận
đã bán" ở trang căn hộ. Gỡ nút mà để lại route thì luật này chỉ đúng trên màn
hình, không đúng trên API — `test_khong_con_route_ghi_nhan_ban_ngoai_man_giao_dich`
giữ cho nó không quay lại.

Bán một căn chưa có lead: sale bấm "Đặt cọc căn này" ở trang căn hộ để tạo lead
trước, rồi chốt ở màn Giao dịch. Hai bước, đổi lại **mọi giao dịch đều có thông
tin liên hệ của người mua**.

Nhãn nằm ở **một chỗ duy nhất**: [`tools/trang_thai.py`](src/agents/tools/trang_thai.py)
cho backend, [`utils/trangThai.js`](interface/frontend/src/utils/trangThai.js) cho
FE. Trước đó `inventory.py` và `so_sanh.py` mỗi bên giữ một bản chép — thêm
trạng thái mà sửa một bên là cùng một căn hiện hai nhãn khác nhau tuỳ vào việc
khách hỏi "VOP397 còn không" hay "so sánh VOP397 với VOP345".

**Trạng thái SUY RA trong VIEW, không lưu thành cột.** [Migration 010](interface/backend/migrations/010_trang_thai_dat_coc.sql)
`LEFT JOIN dat_coc_lead`. Ghi trạng thái vào `salemate_v1` là dựng hai nơi cùng
nắm sự thật — đúng kiểu đã làm 4 căn sai giá ở migration 005. Chatbot vẫn chỉ
ghi vào bảng lead, không đụng tồn kho gốc.

⚠️ **View không được kéo cột nào của lead ra.** Từng dòng `inventory_units` đi
thẳng vào prompt LLM; `ho_ten`/`so_dien_thoai` lọt ra là chảy vào log nhà cung
cấp. Subquery chỉ gom hai boolean.

**Cọc KHÔNG tự hết hạn** — quyết định sản phẩm. Van xả duy nhất là màn hình
`/giao-dich` (sale + admin), chọn "Đã huỷ". Thiếu nó thì cách duy nhất trả căn
về "Còn" là chạy SQL tay trên production.

**Một màn `/giao-dich` cho cả hai vai**: lead đặt cọc và căn đã bán là hai nửa
của cùng một phễu. Admin thấy toàn hệ thống kèm sale phụ trách; sale thấy lead
của mình **cộng lead chưa ai nhận** (`sale_id` rỗng — khách tự đặt) và căn mình
đã bán. Trước đó là ba mục menu trỏ tới ba trang nói về cùng một việc.

**Hai đường ghi lead, cùng một bộ chốt chặn.** Widget chat (tool `dat_coc`) và
nút "Đặt cọc" trên trang căn (`POST /api/dat-coc`, **không cần đăng nhập**).
Cả hai phải: từ chối căn không `available`, chuẩn hoá số điện thoại cùng luật,
và chặn `TOI_DA_GIU_MOI_SO = 3`. Sale đăng nhập rồi bấm nút thì lead ghi thêm
`sale_id`; khách vãng lai để rỗng.

⚠️ **Trần 3 căn/số là phanh chống khoá sạch tồn kho.** Lead `new` làm căn thành
"Đang giữ chỗ" và giữ chỗ không tự hết hạn, nên không có trần thì một người gửi
100 yêu cầu là cả kho thành "hết hàng" cho tới khi có người dọn tay. Hai service
tách nhau nên luật này bị chép hai bản (`src/data/stores/dat_coc_db.py` và
`interface/backend/app/routers/dat_coc.py`) — **sửa một bên là vô nghĩa**, đường
còn lại vẫn mở.

`inventory_search` vẫn trả căn giữ chỗ / đã cọc, kèm `status_label`: cọc huỷ
được, và giấu đi thì khách đang xem dở quay lại thấy căn biến mất không lời giải
thích. Chỉ `sold` mới bị loại.

**Mã căn do WIDGET chèn không tính.** FE gắn `(căn đang xem: VOP758)` vào mọi
câu không có mã căn (`themNguCanh` trong `ChatSidebar.jsx`). Mọi `build_args`
quyết định dựa trên "người dùng CÓ tự nêu mã căn không" **phải** gọi
`bo_ngu_canh_giao_dien()` trước. `inventory_summary` từng quên, nên "Ocean Park
3 còn bao nhiêu căn đang bán?" hỏi lúc đang mở VOP758 thì tool đếm im lặng và
trợ lý trả lời "chưa đủ dữ liệu… căn đang xem là VOP758 thuộc Ocean Park 1".

**Câu ĐẾM: `inventory_search` nhường `inventory_summary`** — nhưng chỉ khi
summary lọc được HẾT tiêu chí (`subdivision`/`building`/`unit_type`). Nó không
biết giá lẫn diện tích, nên "có bao nhiêu căn dưới 4 tỷ" mà nhường thì con số
trả về là đếm cả kho, sai mà nghe rất chắc chắn.

**Đơn vị tiền là TUỲ CHỌN nên số trần dễ bị đọc thành giá.** "khoảng 43m²" từng
ra `price 42,8 – 43,2` TỶ; kho không có căn nào giá 43 tỷ nên trả rỗng, và lượt
gợi ý sau lại dựng "giá 42,8–43,2" từ chính tiêu chí sai đó — khách bấm hai lần
liên tiếp vào hai ngõ cụt. `_rut_dien_tich` chạy TRƯỚC `_rut_gia` và **xoá** phần
đã đọc, nếu không thì "từ 40 đến 50 m2" đẻ thêm `price_min = 40`.

Vì sao `so_sanh_can` phải tồn tại: `inventory_lookup` dùng `re.search` nên chỉ
bắt mã ĐẦU TIÊN. "So sánh VOP619 với VOP893" tra được đúng VOP619, model thiếu
một vế rồi từ chối — khách nhận "chưa đủ dữ liệu" giữa lúc đang cân nhắc mua.
Vòng lặp agent vốn để chữa ca này, nhưng `ENABLE_AGENT_LOOP` mặc định TẮT và
production không bật, nên so sánh phải chạy được ở đường tất định.

`@register_tool` trần (không tham số) vẫn đăng ký tool cho LLM thấy qua
`specs()` nhưng agent **không** tự gọi — dùng cho tool chỉ chạy khi được yêu cầu
tường minh.

Tool **không raise** — trả `ToolResult.failure(...)`. Một tool hỏng không chặn
các tool khác trong cùng lượt.

**Dữ liệu có cấu trúc (giá, tình trạng căn) đi qua tool, không nhét vào Qdrant.**
RAG luôn là bản chụp; giá và tình trạng đổi hàng ngày. Trộn hai đường là tự tạo
hai nguồn số liệu lệch nhau.

### Con số của chính sách cũng là dữ liệu có cấu trúc

[`tools/data/chinh_sach_vay.json`](src/agents/tools/data/chinh_sach_vay.json) giữ
tham số định lượng của chính sách hỗ trợ lãi suất — trần lãi suất, số tháng
khoá, phụ phí từng gói, và **`hieu_luc_den`**. Văn bản vẫn ở Qdrant để trích
dẫn; chỉ con số dùng để TÍNH mới ra đây.

Vì sao không rút số từ văn xuôi bằng model: đã đo được nó bịa. Hỏi "tôi có 1 tỷ,
mua VOP397 thì vay thế nào", model lấy đúng giá từ tool rồi tự thêm "ngân hàng
cho vay lên đến 70-80% giá trị" — không tài liệu nào nói vậy.

Vì sao có `hieu_luc_den`: chính sách bất động sản có hạn. Bản 6%/5 năm chỉ áp
dụng cho khách mua 20/4–20/7/2026 và đã thay bản 9% công bố trước đó một tháng.
`tinh_khoan_vay` đọc ngày để biết còn hiệu lực không — hết hạn thì nói thẳng và
**không gán lãi suất nào**, thay vì rơi về chính sách gần nhất rồi báo cho khách
một ưu đãi họ không được hưởng.

File JSON chứ không phải bảng Postgres vì migration ở dự án này chạy thẳng lên
production; để trong repo thì mỗi lần sửa là một PR có review. Đổi sang DB về
sau chỉ cần thay thân `tai_chinh_sach()`.

## Ảnh căn hộ — ảnh đại diện KHÔNG phải một cột riêng

Ảnh đại diện chỉ là dòng có `sort_order` nhỏ nhất trong `apartment_images`. Cả
ba nơi đọc cùng một thứ tự đó: thẻ ở trang tìm kiếm (`LEFT JOIN LATERAL … LIMIT
1`), gallery trang chi tiết, và tính năng "Modify Object" của widget chat. Nên
đổi bìa một lần là cả ba đổi theo.

**Đừng thêm cột `cover_image_id` hay `is_cover`.** Đó là nơi thứ hai nắm cùng
một sự thật, đúng kiểu đã làm 4 căn sai giá ở migration 005 — và lệch ở đây thì
thẻ tìm kiếm hiện một ảnh còn gallery mở ra một ảnh khác.

Đổi bìa = `_danh_lai_thu_tu()` trong [apartments.py](interface/backend/app/routers/apartments.py):
một câu UPDATE đánh lại `sort_order` thành 0,1,2… với ảnh được chọn kéo lên đầu.
Không "swap hai dòng" được: ảnh nhập từ Google Drive hầu hết đều `sort_order = 0`
nên thứ tự thật do `id` quyết định, tức thứ tự file trong folder Drive — không có
thứ tự nào để mà swap.

| Việc | Đường đi |
|---|---|
| Đổi ảnh đại diện | `PATCH /api/apartments/{ma_can}/images/{id}/dai-dien` (admin) |
| Bỏ ảnh xấu | `DELETE /api/apartments/{ma_can}/images/{id}` (admin) |
| Thay bằng ảnh khác | upload qua `POST …/images` rồi đặt làm đại diện |

Cả ba nút nằm dưới gallery ở trang căn hộ, chỉ admin thấy
([`QuanLyAnh.jsx`](interface/frontend/src/components/QuanLyAnh.jsx)) — lúc chọn
ảnh nào lên bìa thì phải nhìn được cả 4 ảnh ở kích thước thật.

**Bucket `apartment-images` là một bước cài đặt tường minh, không tự sinh.**
Tạo ngày 21/08/2026: public, trần 8MB, chỉ nhận JPG/PNG/WEBP/GIF — khớp đúng
`MAX_IMAGE_BYTES` và `ALLOWED_IMAGE_TYPES` mà router đang kiểm, để file lạ không
lọt vào bằng đường nào khác. Trước đó project Supabase **không có bucket nào**
và mọi lần upload đều trả 400 "Bucket not found"; không ai biết vì toàn bộ ảnh
trong DB là link Google Drive, đường Storage chưa từng chạy thật.

Backend cố ý KHÔNG tự tạo bucket lúc upload — đó đúng cái bẫy `ensure_table()`
đã ghi ở mục đặt cọc: hạ tầng do code lặng lẽ dựng lên là hạ tầng không ai review,
và ở đây thứ bị bỏ qua sẽ là "bucket này công khai hay riêng tư".

Public là bắt buộc vì `public_url()` dựng link `/object/public/…` và khách chưa
đăng nhập phải xem được ảnh trên portal. Đổi sang private thì phải đổi sang
signed URL có hạn, không chỉ đổi một cờ.

Hai chốt của endpoint xoá: `WHERE id = %s AND ma_can = %s` (thiếu vế sau thì URL
của căn này sửa được ảnh căn kia), và **xoá dòng DB trước, xoá object Storage
sau, lỗi Storage không làm hỏng request** — trang đọc từ DB, một file mồ côi
trong bucket thì không ai thấy, còn trả lỗi sau khi dòng đã xoá là bắt admin bấm
lại một việc đã xong.

## Streaming và hiện suy luận

Widget đọc SSE để chữ hiện dần, kèm dòng trạng thái "trợ lý đang làm gì".

```
lõi AI  /api/v1/chat/stream      phát start · route* · token* · sources · done
   ↓
backend /api/chat/stream         dẫn nguyên ống, KHÔNG parse
   ↓
FE      streamChat()             fetch + ReadableStream, không dùng EventSource
                                 (EventSource chỉ gửi được GET)
```

Sự kiện tiến trình đều mang nhãn `ROUTE`, phân biệt bằng `data.step`:
`router` · `tools` · `retrieve`. `/api/chat` bản không stream vẫn giữ nguyên
contract `{message, history} -> {reply}` cho client đơn giản và cho test.

**Đường stream không chạy qua graph** — nó cần chen event vào giữa các bước. Bù
lại nó lấy thứ tự node từ `CONTEXT_NODES` trong `graph.py`, nên thêm node mới
vào graph là stream tự chạy theo. Đừng liệt kê tay node ở `service.py`: đã có
lần làm vậy và đường stream lặng lẽ bỏ qua node `tools`.

## Trích nguồn — chỉ hiện thứ ĐÃ DÙNG

Hai đường sinh nguồn đều trả về "đã tra cứu", không phải "đã dùng":
`RetrieveNode` tạo một `Citation` cho **mọi** chunk lấy về, `ToolsNode` tạo cho
mọi tool chạy được. [`src/agents/nguon.py`](src/agents/nguon.py) lọc lại trước
khi hiện.

**Một TÀI LIỆU một dòng.** `RetrieveNode` tạo một `Citation` cho mỗi CHUNK, và
truy hồi thường lấy 3–5 đoạn của cùng một tài liệu — nên dòng "Nguồn" từng hiện
y hệt một cái tên ba lần. `_bo_trung` khử theo `doc_id`, và xếp tài liệu đóng
góp **nhiều đoạn nhất** lên đầu: người đọc thấy hai cái tên thì câu hỏi đầu tiên
là "tin cái nào", thứ tự phải trả lời được câu đó.

Đếm đoạn chứ không xếp theo điểm vì `KeywordOverlapReranker` cho điểm rất phẳng
— đo thật, tài liệu chính (4/5 đoạn) được 0,650 còn tài liệu phụ (1/5 đoạn) được
0,620. Số đoạn nói rõ tài liệu nào dựng nên câu trả lời, điểm thì không.

Trần `TOI_DA_NGUON_TAI_LIEU = 3` cũng đếm **tài liệu**, không đếm đoạn — trước
đây 3 đoạn của một tài liệu đã chạm trần và hai tài liệu khác bị loại oan.

| Loại nguồn | Luật giữ |
|---|---|
| `kind="db"` (mã căn) | mã căn xuất hiện trong câu trả lời |
| `kind="doc"`, lượt CÓ dữ liệu tool | model trích tên tài liệu tường minh — nhận cả **tên rút gọn** trong dấu `[…]`, tối thiểu 15 ký tự |
| `kind="doc"`, lượt KHÔNG có tool | giữ 3 cái điểm cao nhất |

Lọc ở đâu: đường stream lọc ngay trước khi phát `SOURCES` (đó là lý do event này
bị giữ lại từ `_prepare_context` rồi mới phát sau khi hết token); đường graph lọc
trong `GuardrailNode._all_citations`. Cả hai cần `answer` để đối chiếu.

**Lưới an toàn:** lượt có dữ liệu tool mà không nguồn tool nào lọt (câu trả lời
nói "căn này" thay vì nhắc mã) thì giữ lại vài cái đầu. Xoá sạch nguồn là xoá
đúng thứ chứng minh trợ lý không bịa.

**Nhưng lưới chỉ cứu KHẲNG ĐỊNH.** `_co_khang_dinh_ve_can` hỏi câu trả lời có
con số kèm đơn vị, hoặc có trỏ vào một căn cụ thể, hay không — chưa nói gì thì
không có gì để chứng minh. Thiếu chốt này thì lượt trợ lý **hỏi ngược** để làm
rõ tiêu chí vẫn dựng lên ba mã căn dưới một câu không nhắc tới căn nào; đã xảy
ra thật với "Căn ở Ocean Park 1". Con số phải kèm đơn vị vì chữ số trần có ở
khắp nơi vô hại — "Ocean Park 1", "tòa S2".

**Kết quả TỔNG HỢP không có mã căn để trỏ vào.** Tool khai `nhan_nguon` (thuộc
tính tuỳ chọn, đọc bằng `getattr` nên không đụng hợp đồng đóng băng) để dòng
"Nguồn" hiện "Dữ liệu tồn kho" thay vì tên tool hay cả đoạn description. Bộ lọc
cũng phải cho nhãn không-hình-mã-căn đi qua mà không đối chiếu với câu chữ —
"còn 30 căn đang bán" không bao giờ chứa chuỗi "Dữ liệu tồn kho".

Nhãn nguồn của tool là **mã căn**, không phải câu đầu trong description. Hàm
`_ma_can_trong` phải đi xuống một tầng vì `inventory_search` trả
`{tong_so_khop, can_hien_thi: [...]}` chứ không trả thẳng mảng căn — bản đầu chỉ
dò tầng ngoài nên cả description dài ngoằng của tool leo lên dòng "Nguồn".

**Tool đọc số từ tài liệu thì nguồn phải là TÀI LIỆU đó.** `tinh_khoan_vay` lấy
trần lãi suất và các gói 18/24/30/36/60 tháng từ `chinh_sach_vay.json`, mà file
đó khai sẵn `doc_id` trỏ về tài liệu gốc — nó trả `source` là `doc_id` ấy, nên
dòng "Nguồn" hiện tên tài liệu và bấm vào mở được. Trước đây hiện
`"tinh_khoan_vay"`: một cái tên máy, bấm không ra gì.

⚠️ Nhưng vẫn `kind="db"`. **`kind` và tiền tố `doc_id` là hai khái niệm khác
nhau**: `kind` nói nguồn ĐẾN TỪ đâu (`db` = tool đã dùng thật, `doc` = truy hồi
chỉ mới lấy về), tiền tố nói nó TRỎ VÀO đâu (`knowledge:` mở được trang tài
liệu). Đặt `kind="doc"` cho nguồn tool là tự bắn vào chân — luật lọc bắt nguồn
tài liệu phải được model gọi tên, đúng cho chunk truy hồi nhưng sai cho tool.
FE quyết định bấm được hay không theo **tiền tố `doc_id`**, không theo `kind`.

**Từ chối MỘT PHẦN vẫn phải có nguồn.** "Căn VOP962 giá 2,7 tỷ. Vay 70% khoảng
1,89 tỷ. Mình chưa có đủ dữ liệu về lãi suất…" có cụm từ chối và ngắn dưới 400
ký tự nên `la_loi_tu_choi` gọi nó là từ chối, xoá sạch nguồn — đúng lúc hai con
số đó là thứ khách mang đi hỏi ngân hàng. `loc_nguon_da_dung` ràng thêm
`_co_khang_dinh_ve_can`; **không sửa `la_loi_tu_choi`** vì bộ eval chấm cột
`phai_tu_choi` bằng chính hàm đó.

**Mọi chỗ chạy tool đều phải gọi `_nguon_cua_tool` của `ToolsNode`, đừng tự dựng
`Citation`.** `OrchestratorNode` bản đầu chép cách làm đơn giản của `ActNode`
(lấy câu đầu trong description làm nhãn) và tái tạo đúng lỗi trên: cùng câu hỏi
cho ra hai kiểu trích nguồn tuỳ vào việc cổng leo thang có mở hay không.

FE hợp nhất hai nguồn: dấu `[Mã căn]` model tự viết, và event `sources`. Không
được bỏ vế thứ hai — production chạy `gpt-4o-mini` và model đó bỏ qua luật trích
nguồn, dòng "Nguồn" biến mất hẳn trong khi local dùng `gpt-4o` thì vẫn có.

⚠️ **Nhãn model tự viết KHÔNG còn được tính là nguồn.** FE chỉ hiện danh sách
backend duyệt (`nguonThat`), vì hai lý do đã xảy ra thật: model đọc mục "Nguồn
tham khảo" cuối tài liệu, thấy `[Sang tên Sổ đỏ 2026 — LuatVietnam](https://…)`
trùng đúng cú pháp trích dẫn rồi chép làm nhãn — dòng "Nguồn" trỏ sang một bài
báo ngoài trong khi trợ lý đọc tài liệu nội bộ; và nhãn model tự nghĩ không có
`doc_id` nên không bấm vào đâu được.

`gomNguon` vẫn chạy để GỠ dấu `[…]` khỏi thân bài — đó là cú pháp nội bộ.

⚠️ **Đường thứ nhất KHÔNG đi qua bộ lọc nào.** `gomNguon` trong `CauTraLoi.jsx`
rút thẳng dấu `[…]` từ thân bài, nên mọi luật ở `nguon.py` đều vô hiệu với nó:
backend lọc sạch nguồn xong, FE vẫn dựng lại đúng những mã vừa bị loại. Đã xảy
ra thật — trợ lý hỏi "bạn muốn lọc theo tiêu chí nào?" mà dưới đó có
"Nguồn: VOP758, VOP247, VOP619", và thân bài cụt thành "…và diện tích **như.**"
sau khi FE gỡ dấu.

Nên backend nói thẳng qua `data.cho_trich_nguon` của event `done`: `False` thì
FE vẫn **gỡ** dấu khỏi thân bài nhưng **không** dựng dòng "Nguồn". Quyết định
nằm ở một chỗ duy nhất là Python; FE chỉ nghe theo. `undefined` (stream đứt
giữa chừng) giữ nguyên hành vi cũ để không mất sạch nguồn vì một lỗi mạng.

## Gợi ý câu hỏi tiếp theo — và đường dẫn tới đặt cọc

[`src/agents/suggest.py`](src/agents/suggest.py) ráp tối đa 4 câu hỏi bấm được sau
mỗi lượt, gửi ra FE qua `data.options` của event `done`.

**Đích của dãy nút không phải hỏi cho vui.** Nó dẫn khách từ danh sách về một
căn, từ một căn sang so sánh và tài chính, rồi tới giữ chỗ. Bước cuối có thật:
tool `dat_coc` ghi lead vào Postgres cho đội sale gọi lại.

Hai tầng sinh gợi ý:

| Tầng | Khi nào | Vì sao |
|---|---|---|
| `goi_y_bang_model` | mặc định | model rẻ (`llm_model_fast`) đọc câu vừa trả lời rồi viết gợi ý bám đúng mạch — khuôn cố định lộ ra sau vài lượt, khách thôi không đọc nút nữa |
| `goi_y_tiep_theo` | model hỏng / trả rác | lưới an toàn, suy từ state, không gọi model |

Gọi SAU khi chữ đã stream hết nên khách đang đọc, không thấy nhịp chờ. Mọi lỗi
đều nuốt và rơi về khuôn — mất dãy nút thì tiếc, mất câu trả lời thì hỏng.

Không làm thành `@register_tool`: `ToolsNode` chạy TRƯỚC `generate` và kết quả
tool đi thẳng vào prompt, còn gợi ý sinh ra SAU câu trả lời và không được vào
prompt.

Ba luật, đừng gỡ:

| Luật | Chặn chuyện gì |
|---|---|
| Mọi câu qua `_tra_loi_duoc`, kể cả câu model viết | nút bấm dẫn vào "chưa đủ dữ liệu" |
| Câu tự chứa đủ tiêu chí | `build_args` chỉ đọc câu hiện tại, không nhớ lượt trước |
| Mã căn và tên tài liệu lấy từ lượt này | model từng chào "ưu đãi Ocean Park 1" trong khi kho chỉ có OP2, OP3 |

`_tra_loi_duoc` có **hai** tầng. Tầng một hỏi registry xem có `build_args` nào
nhận câu đó không, nên thêm tool mới là tự động được tính. Tầng hai sinh ra từ
một lỗ hổng test bắt được: "Ưu đãi Ocean Park 1 có gì" lọt qua tầng một vì
`extract_criteria` thấy "Ocean Park 1" rồi rút ra phân khu — tool tìm căn chạy và
trả về danh sách căn hộ, trong khi khách bấm vào để đọc ưu đãi và kho không hề có
tài liệu ưu đãi cho OP1. Nên câu hỏi về chủ đề tài liệu còn phải khớp một tài
liệu đã truy hồi thật.

Nhánh chưa đủ dữ liệu cũng có gợi ý: nhặt lại tiêu chí từ lượt user gần nhất rồi
trải ra ba phân khu. Chỉ dùng lịch sử để **dựng gợi ý** — `extract_criteria` giữ
nguyên hành vi chỉ đọc câu hiện tại, nới chỗ đó là nới rủi ro tra nhầm sang tiêu
chí người dùng đã bỏ.

### Tool `dat_coc` — bước chốt

[`src/agents/tools/dat_coc.py`](src/agents/tools/dat_coc.py) ghi lead vào bảng
`dat_coc_lead` ([migration 009](interface/backend/migrations/009_dat_coc_lead.sql)).

**Tool chạy ngay cả khi khách chưa cho số điện thoại** — chủ ý, không phải thiếu
kiểm tra. Câu "đặt cọc căn VOP397" phải được nhận thì trợ lý mới có cớ hỏi xin
số; đòi đủ số mới chạy thì câu đó rơi vào nhánh "chưa đủ dữ liệu" và khách bị từ
chối đúng lúc muốn mua, còn bộ lọc gợi ý cũng loại luôn nút "Đặt cọc". Thiếu
thông tin thì tool trả `trang_thai="can_bo_sung"` kèm `con_thieu` để `generate`
hỏi xin đúng thứ đó.

**Không bao giờ nêu số tiền cọc, thời hạn giữ chỗ hay mức phạt** — hệ thống không
có dữ liệu nào về chúng. Prompt v6 cấm, và test khẳng định `data` của tool không
chứa đơn vị tiền.

Số điện thoại **không** được trả lại vào `data`: `data` đi vào prompt, rồi vào log
của nhà cung cấp LLM. Bảng có RLS, log thì không.

⚠️ **`ensure_table()` KHÔNG được tạo bảng trên Postgres.** Hàm này chạy ở đầu
mọi thao tác, và trên database thật nó đã lặng lẽ tạo `dat_coc_lead` trước khi
migration 009 kịp chạy — sau đó `CREATE TABLE IF NOT EXISTS` của 009 thấy bảng
đã có nên bỏ qua im lặng. Bảng SQLAlchemy dựng ra thiếu DEFAULT (nên INSERT bằng
SQL thuần ném `NotNullViolation`), thiếu CHECK, thiếu unique index chống trùng,
và **thiếu RLS** — bảng chứa tên với số điện thoại khách thật mở cho role `anon`.
[Migration 011](interface/backend/migrations/012_dat_coc_lead_va_schema.sql) vá
lại. Trên Postgres, **migration là nguồn sự thật duy nhất của schema**.

Hệ quả cho code: `server_default` chứ không chỉ `default` — `default` của
SQLAlchemy là mặc định phía Python, chỉ áp dụng khi ghi qua SQLAlchemy. Và câu
INSERT ở portal ghi thẳng `trang_thai`/`created_at`, không dựa vào DEFAULT của
cột, để không phụ thuộc việc migration nào đã chạy ở môi trường nào.

⚠️ `tests/conftest.py` vá `get_dat_coc_db` ở **cả hai** chỗ — module tool và
module store. Tồn kho chỉ vá module tool là đủ vì nó chỉ đọc; tool này **ghi**.
Đã xảy ra thật khi viết test cho nó: một dòng `from src.data.stores.dat_coc_db
import get_dat_coc_db` để đọc lại kết quả đã tạo bảng thật trên Supabase.

## Tracing

`trace()` trong `src/core/logging.py` dùng `ContextVar` — mọi dòng log phát ra
trong một lượt hỏi tự mang `session_id`. Lọc log theo một session là thấy đủ
đường đi: router → tools → retrieve → generate, kèm thời gian từng chặng.

```python
with trace(session_id=sid, mode="stream"):
    ...   # mọi log bên trong đều có hai trường này
```

Hai người hỏi cùng lúc không trộn log của nhau vì `ContextVar` tách theo task.

## Lệnh

```bash
make run-api    # API sản phẩm  http://localhost:8000/docs
make run-ai     # lõi AI + RAG  http://localhost:8001/docs
make fe         # frontend      http://localhost:5173
make infra      # Qdrant + Postgres bằng Docker
make check      # lint + format + test lõi AI — CHẠY TRƯỚC KHI PUSH
make check-all  # check + test API sản phẩm
make cov        # test + coverage (gate 60%)
```

Windows: `make` cần thêm vào PATH sau khi cài — xem [RUN.md](RUN.md).

## Quy ước code

**Python** — Python 3.11, type hint đầy đủ, hàm ≤30 dòng, không `except:` trần,
không hardcode secret. Lỗi nghiệp vụ raise lớp trong `src/core/exceptions.py`,
**không** raise `HTTPException` ngoài tầng `api/`.

**JavaScript** — React function component, component nhỏ, mọi lời gọi API đi qua
`interface/frontend/src/api/`. Không có TypeScript trong dự án này.

**Giao diện** — tiếng Việt, câu chủ động, sentence case. Màu/bo góc/font lấy từ
biến CSS trong `interface/frontend/src/styles/global.css`, không hardcode trong
component.

**Thông điệp lỗi** — nói rõ chuyện gì và cách khắc phục. Không xin lỗi sáo rỗng,
không lộ stack trace ra ngoài.

**Test** — không test nào được gọi OpenAI, Qdrant hay **Postgres** thật. Dùng
`FakeEmbedder`, `ScriptedProvider`, `InMemoryVectorStore`, hoặc
`container.override(...)`. `tests/conftest.py` có fixture autouse cấp SQLite
rỗng cho tool tồn kho — cần dữ liệu thì tự `monkeypatch` `get_inventory_db`
trong module test của mình.

Vì sao có fixture đó: `get_inventory_db()` đọc `get_settings()` toàn cục, tức
`.env` của máy, tức Supabase **production**. Đã có lần thêm một tool làm test cũ
bắn thẳng vào database thật rồi đổi kết quả.

## Deploy

Chi tiết ở [DEPLOY.md](DEPLOY.md). Ba điều cần biết trước khi đụng vào:

**Có repo thứ hai.** Render không cài được GitHub App lên org của BTC, nên có
bản sao một chiều ở tài khoản cá nhân, chỉ để Render và Vercel đọc. Repo org vẫn
là nguồn sự thật duy nhất — **không commit vào mirror**. Đồng bộ bằng
`make sync-deploy`, nhớ chạy sau mỗi lần merge PR.

**Chỉ deploy nhánh `develop`.** Nhánh `main` còn là bản cũ chưa có thư mục
`interface/`, trỏ service vào đó là build hỏng.

**Một Supabase project dùng chung** cho mọi môi trường. Sửa dữ liệu khi test là
người dùng thấy ngay, và chạy migration là chạy thẳng lên production.

## Git

`main` ← `develop` ← nhánh cá nhân (`huy` · `dat` · `viet` · `phuc`).

Commit: `feat:` `fix:` `docs:` `test:` `refactor:` `chore:`.
Commit nhỏ và đều — BTC xem git history để đánh giá tiến độ.

Không `git push --no-verify`, không sửa/xoá `.ai-log/` — hook ghi log AI là yêu
cầu bắt buộc của BTC.

**Ghi log AI — hai loại file, hai luật khác nhau:**

| | File | Luật |
|---|---|---|
| Cấu hình từng AI tool | `.claude/settings.json` · `.codex/hooks.json` · `.cursor/hooks.json` · `.gemini/settings.json` · `.github/hooks/hooks.json` | **Không commit.** Đã gitignore. Mỗi máy tự tạo theo mẫu trong [`.agents/rules/ai-log-hook.md`](.agents/rules/ai-log-hook.md) |
| Script hạ tầng | `scripts/_pyrun.*` · `scripts/log_*.py` · `scripts/submit_log.py` · `scripts/setup_hooks.*` | Vẫn commit, nhưng **đóng băng** — không sửa trong PR tính năng, muốn sửa thì PR riêng |

Nội dung log (`.ai-log/*.jsonl`) chưa bao giờ nằm trong repo — nó bắn thẳng lên
server BTC. Repo chỉ giữ phần cơ khí để clone mới dựng lại được.

## Definition of Done

Có test · `make check` xanh · đã review · đã merge vào `develop` · tài liệu liên
quan đã cập nhật.
