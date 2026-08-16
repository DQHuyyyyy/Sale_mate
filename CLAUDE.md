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

Mọi lựa chọn lấy từ `Settings`, **không hardcode** — đổi hành vi bằng biến môi
trường (`ENABLE_RAG`, `RERANKER`, `QDRANT_URL`), không phải sửa code rồi commit.

Test luôn dùng vector store trong bộ nhớ: không test nào được gọi Qdrant thật.

## Dữ liệu RAG

Một dòng lệnh duy nhất cho mọi thao tác dữ liệu:

```bash
python -m src.cli status            # vector store đang có gì
python -m src.cli ingest --all      # nạp mọi nguồn
python -m src.cli search "câu hỏi"  # thử truy hồi
python -m src.cli eval              # đo trên bộ câu hỏi vàng
```

Thêm nguồn mới: viết hàm `ingest_<tên>()` trong `src/data/ingest.py` rồi thêm
một dòng vào `SOURCES` cuối file đó. **Không tạo script rời** — bài học cũ: bốn
script tự dựng `QdrantVectorStore` riêng nên chạy tốt, trong khi `bootstrap.py`
vẫn dùng in-memory, web app đứt khỏi dữ liệu nhiều ngày mà không ai phát hiện.

**Dữ liệu tồn kho KHÔNG đi đường này.** Giá và tình trạng căn nằm ở Postgres,
tool đọc trực tiếp — xem mục "Thêm một tool". `inventory_units` là VIEW trên
`salemate_v1` ([migration 005](interface/backend/migrations/005_inventory_units_view.sql)),
nên chatbot và portal luôn nói cùng một con số. Trước đó nó là bảng sao chép và
đã trôi lệch 4 căn sai giá.

### Qdrant chỉ chứa `doc_kind="policy"`

`SOURCES` giờ chỉ còn `knowledge`. Ba nguồn tin rao đã bị gỡ và 871 chunk của
chúng đã xoá khỏi Qdrant:

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
