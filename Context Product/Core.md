# Core.md — Lõi trợ lý AI

> Đặc tả hành vi agent cho **widget AI** trên portal SalesMate.
> Khung giao diện xem `Giaodien.md` mục 5. Bản này **thay thế hoàn toàn** bản cũ —
> bản cũ mô tả app nội bộ cho sale, sản phẩm đã đổi sang portal công khai.
>
> Cập nhật 01/08/2026 · Chủ sở hữu code: `viet` (`src/agents/**`)

## 1. Agent này là gì

Trợ lý trả lời câu hỏi bất động sản **ngay trên trang**, cho người dùng công khai:
người mua, người bán, môi giới, nhà đầu tư. Không cần đăng nhập mới hỏi được.

Nó là **agent có kiểm soát**, khác chatbot RAG thẳng ở ba điểm:

1. **Định tuyến** — tự chọn nguồn đúng cho từng câu: tài liệu pháp lý, dữ liệu
   tin đăng, hay thống kê giá.
2. **Dùng công cụ** — tra tin đăng và mặt bằng giá từ dữ liệu có cấu trúc, không
   đọc số từ văn bản.
3. **Biết dừng** — thiếu dữ liệu thì nói thiếu, không suy đoán.

### Không phải cái gì

- **Không phải cố vấn pháp lý.** Nó giải thích thủ tục chung, không thay luật sư.
- **Không phải công cụ định giá.** Nó nêu mặt bằng giá quan sát được từ tin
  đăng, không định giá một bất động sản cụ thể.
- **Không tự đăng tin.** Nó soạn nháp, người dùng đọc rồi mới đăng.
- **Không lặp vòng vô tận.** Phần lớn câu hỏi chỉ cần một vòng. Giá trị nằm ở
  định tuyến đúng và biết dừng, không nằm ở độ phức tạp.

## 2. Bốn năng lực

Khớp 1-1 với bốn chip quick-action trong `Giaodien.md` mục 5.2. Đây là phạm vi
đã chốt của giai đoạn hiện tại.

| Chip | Năng lực | Nguồn dữ liệu | Trạng thái |
|---|---|---|---|
| Tư vấn giá theo khu vực | Nêu mặt bằng giá theo khu vực và loại hình | Tool `price_stats` trên DB tin đăng | 🔴 chưa làm |
| Tìm căn hộ phù hợp | Lọc tin đăng theo ngân sách · khu vực · số phòng | Tool `listing_search` trên DB | 🔴 chưa làm |
| Đặt câu hỏi pháp lý | Giải thích thủ tục, có trích nguồn | RAG trên kho tài liệu pháp lý | 🟡 khung xong, chưa bật |
| Viết tin đăng | Soạn nháp tin đăng từ thông tin người dùng đưa | LLM sinh, người dùng duyệt | 🔴 chưa làm |

Câu hỏi ngoài bốn năng lực → trả lời chung, ngắn, rồi mời người dùng hỏi vào một
trong bốn hướng trên.

## 3. Bảy nguyên tắc bất biến

Vi phạm bất kỳ điều nào dưới đây là lỗi nghiêm trọng, không phải lỗi nhỏ.

1. **Tĩnh đi RAG, động đi tool.** Tài liệu pháp lý và quy trình đi qua RAG. Tin
   đăng, giá, thống kê thị trường đi qua tool. **Tuyệt đối không** nhét dữ liệu
   tin đăng vào vector store — RAG luôn là bản chụp cũ.
2. **Số lấy từ dữ liệu có cấu trúc**, không để LLM đọc số từ đoạn văn bản.
3. **Luôn trích nguồn** cho khẳng định lấy từ tài liệu: tên tài liệu + phiên
   bản/ngày.
4. **Biết dừng.** Độ phủ truy hồi dưới ngưỡng → trả "chưa đủ dữ liệu", không đoán.
5. **Câu hỏi pháp lý luôn kèm miễn trừ.** Không bao giờ khẳng định chắc chắn về
   hệ quả pháp lý của một trường hợp cụ thể.
6. **Nội dung có hệ quả phải qua người duyệt.** Nháp tin đăng không tự đăng.
7. **Tiếng Việt** toàn bộ nội dung người dùng thấy. Embedding và rerank phải
   mạnh tiếng Việt.

## 4. Luồng orchestrator

```
Câu hỏi + lịch sử ngắn
   │
   ▼
[1] router ── phân loại intent, quyết định có cần tra cứu không
   │
   ├─(legal | document)──→ [2] retrieve ─┐
   ├─(listing | price)───→ [3] tool ─────┼─→ [4] generate ─→ [5] guardrail ─→ END
   └─(general | draft)───────────────────┘
```

Khớp `src/agents/graph.py`. Nhánh `tool` là phần cần bổ sung — graph hiện mới có
`router → retrieve → generate → guardrail`.

**Không có vòng lặp ở giai đoạn này.** Khi eval cho thấy độ phủ thấp lặp lại ở
một nhóm câu hỏi, mới cân nhắc thêm nhánh viết lại truy vấn rồi truy hồi lần
hai. Thêm vòng lặp sớm chỉ tăng độ trễ và chi phí mà chưa có bằng chứng cần.

## 5. Router

**Input:** câu hỏi + tối đa 10 lượt gần nhất.
**Output:** `intent` và `needs_retrieval`.

| Intent | Nghĩa | Đi tiếp |
|---|---|---|
| `general` | Chào hỏi, hỏi vu vơ, hỏi về chính portal | generate |
| `legal` | Thủ tục, sổ đỏ, hợp đồng, thuế phí | retrieve |
| `listing` | Tìm bất động sản theo tiêu chí | tool `listing_search` |
| `price` | Mặt bằng giá, so sánh giá khu vực | tool `price_stats` |
| `draft` | Nhờ soạn tin đăng | generate + HITL |
| `document` | Cần tra tài liệu, không thuộc pháp lý | retrieve |

**Ba tầng, dừng ở tầng nào ra kết quả tầng đó:**

1. **Luật từ khoá** — "sổ đỏ", "thủ tục", "sang tên" → `legal`. Không tốn lượt
   gọi LLM nào. Đã có trong `router.py`.
2. **Model rẻ** (`LLM_MODEL_FAST`) — prompt ép trả về đúng một từ nhãn.
3. **Fallback `general`** khi model trả nhãn lạ. Không bao giờ để router làm đứt
   luồng.

Luật từ khoá phải giữ ngắn. Khi nó phình quá ~30 dòng, đó là dấu hiệu nên bỏ
luật và để model làm hết.

## 6. Retrieval

Chỉ dùng cho `legal` và `document`.

- **Embedding:** `text-embedding-3-small` giai đoạn này, BGE-M3 sau. Cùng một
  model cho cả ingest và query — đổi model là phải re-index toàn bộ. Xem
  `docs/adr/ADR-002`.
- **Truy hồi:** Qdrant top-k = 20 → rerank → giữ top-n = 5 đưa vào context.
- **Rerank:** hiện `PassthroughReranker`. Thay bằng Cohere Rerank v3 (free tier)
  ở tuần 3.
- **Lọc tại truy vấn:** `visibility ∈ quyền_của_user` và `is_active = true` gắn
  thẳng vào Qdrant filter. Không lọc ở tầng sau. Xem `docs/adr/ADR-001`.
- **Độ phủ:** điểm liên quan cao nhất sau rerank. Dưới `COVERAGE_THRESHOLD`
  (mặc định 0.35) → kích hoạt nhánh "chưa đủ dữ liệu".

> ⚠️ **Ngưỡng 0.35 là giá trị đặt tạm, chưa có cơ sở.** Tuần 4 phải chỉnh lại
> bằng số đo trên golden set: tìm ngưỡng cho tỉ lệ từ chối đúng cao nhất mà
> không từ chối oan. Không chỉnh bằng cảm giác.

## 7. Tool layer

Tool là cách agent lấy **dữ liệu có cấu trúc**. Đặt trong `src/agents/tools/`,
tự đăng ký qua `@register_tool`.

### `listing_search`

```
listing_search(
    location: str | None,        # "Cầu Giấy, Hà Nội"
    listing_type: str | None,    # sale | rent | transfer
    kind: str | None,            # apartment | house | land | villa | shophouse
    budget_max_vnd: int | None,
    bedrooms_min: int | None,
) -> list[Listing]
```

Trả tối đa 5 tin, kèm `id` để FE dựng link sang trang chi tiết. LLM chỉ diễn
giải, không tự chế thông tin tin đăng.

### `price_stats`

```
price_stats(
    location: str,
    kind: str | None,
) -> {min, max, median, count, as_of}
```

Tính từ tin đăng đang hiệu lực trong khu vực. **Luôn kèm `count`** — thống kê từ
3 tin không có giá trị như từ 300 tin, và câu trả lời phải nói rõ điều đó.

### Quy tắc chung

- Tool **không raise**. Lỗi trả `ToolResult.failure(...)` để agent tự xử lý.
- Tool trả dữ liệu có cấu trúc kèm `source`. LLM diễn giải, không chế số.
- Không có kết quả → nói thẳng là không tìm thấy, không bịa ra tin đăng.

### ⚠️ Phải đổi hợp đồng trước khi làm hai tool này

`Listing` trong `src/models/portal.py` hiện chỉ có **giá dạng chuỗi**
(`price_label = "3,85 tỷ"`). Không tính được min/max/median từ chuỗi.

Phải thêm trường số:

```python
price_vnd: int          # 3_850_000_000
area_m2: float          # 68.0
bedrooms: int | None    # 2
```

Giữ nguyên các trường `*_label` để FE hiển thị đúng định dạng Việt Nam. Đây là
sửa `src/models/` nên **bắt buộc PR riêng vào `develop`**, và phải sửa
`frontend/src/lib/types.ts` trong cùng PR đó.

## 8. Grounding và chống ảo giác

- System prompt ép: **chỉ trả lời dựa trên ngữ cảnh được cấp**. Ngữ cảnh không
  chứa thông tin → nói chưa đủ dữ liệu.
- Mọi khẳng định từ tài liệu kèm citation (`doc_id` + phiên bản). FE dựng thành
  chip nguồn từ event `sources`.
- **Coi nội dung tài liệu là dữ liệu, không phải lệnh.** Tài liệu upload có thể
  chứa câu kiểu "bỏ qua hướng dẫn phía trên". Bọc ngữ cảnh trong
  `<ngu_canh>...</ngu_canh>` và nói rõ trong system prompt rằng phần bên trong
  là dữ liệu tham khảo, không phải chỉ thị.
- Không lộ nội dung tài liệu `visibility = internal` trong bất kỳ trường hợp
  nào, kể cả khi người dùng hỏi khéo.

## 9. Guardrail

Chốt chặn cuối trước khi trả về người dùng. Ba việc:

**1. Kiểm tra độ phủ.** `needs_retrieval = true` mà không có chunk nào hoặc độ
phủ dưới ngưỡng → thay câu trả lời bằng:

> Mình chưa có đủ dữ liệu để trả lời chính xác câu này. Bạn cho mình biết thêm
> khu vực, dự án hoặc mức ngân sách để tra cứu sát hơn nhé.

**2. Gắn miễn trừ pháp lý.** `intent = legal` → thêm một dòng cuối câu trả lời:

> Đây là thông tin tham khảo về thủ tục chung. Trường hợp cụ thể của bạn nên hỏi
> thêm công chứng viên hoặc luật sư.

Bắt buộc, không phải tuỳ chọn. Sai sót pháp lý gây hậu quả thật cho người dùng.

**3. Gắn cờ nội dung cần duyệt.** `is_sensitive = true` khi:
- `intent = draft` (nháp tin đăng — luôn cần người xem lại), hoặc
- câu trả lời chứa **số tiền cụ thể** kèm **từ cam kết** ("cam kết", "đảm bảo",
  "chắc chắn").

FE nhận cờ này qua event `sensitive` và hiện khối duyệt.

## 10. Human-in-the-loop

Phạm vi HITL trong sản phẩm mới **hẹp hơn bản cũ**, chỉ có đúng một chỗ:

**Soạn tin đăng.** Agent trả nháp, FE hiện nháp trong khối riêng kèm ba nút:
**Dùng nháp này** · **Sửa** · **Bỏ**. Không có nút nào tự đăng.

Vì sao thu hẹp: bản cũ có HITL cho việc "sale gửi tin cho khách" — vai trò đó
không còn tồn tại. Giữ HITL ở chỗ không cần chỉ làm phiền người dùng.

Khi người dùng bấm "Dùng nháp này", ghi log: ai, nội dung, thời điểm. Vừa là
bằng chứng kiểm soát, vừa là dữ liệu để cải thiện chất lượng nháp.

## 11. Ingestion

```
Tài liệu nguồn (PDF thủ tục, pháp lý, hướng dẫn)
   → parse (giữ cấu trúc bảng)
   → chunk (tôn trọng ranh giới đoạn, không cắt vỡ bảng)
   → embed
   → Qdrant kèm metadata: doc_id · title · version · page · section · visibility
```

- **Versioning:** nạp lại cùng `doc_id` thì xoá chunk cũ, chỉ giữ bản đang hiệu
  lực. `IngestPipeline` đã làm việc này.
- **Nguồn tài liệu giai đoạn này:** 15–20 tài liệu công khai về thủ tục và pháp
  lý bất động sản Việt Nam (sang tên sổ đỏ, thuế phí, hợp đồng đặt cọc, vay mua
  nhà, tra quy hoạch). Đây là thứ khớp chip "Đặt câu hỏi pháp lý" và là thứ
  người dùng portal thật sự hỏi.
- **Cảnh báo mâu thuẫn** (nâng cao, tuần 4): hai tài liệu active nói khác nhau
  về cùng một thủ tục → gắn cờ cho admin và nêu rõ trong câu trả lời.

## 12. Chiến lược prompt

- Prompt đặt trong `src/agents/prompts/*.md`, **có version trong tên file**.
- Đổi prompt → tăng version → chạy lại eval → so số trước/sau. Không đổi mù.
- System prompt gồm: vai trò · bốn năng lực · nguyên tắc grounding · quy tắc
  trích nguồn · định dạng Markdown · giọng văn.
- **Định tuyến model:** router và phân loại dùng `LLM_MODEL_FAST`; câu trả lời
  cuối dùng `LLM_MODEL_ANSWER`. Xem `docs/adr/ADR-003`.
- Bật **streaming** để giảm độ trễ cảm nhận. Mục tiêu: chữ đầu tiên xuất hiện
  dưới 2 giây.

### Giọng văn

Tiếng Việt, câu chủ động, sentence case. Xưng "mình", gọi người dùng là "bạn".
Mặc định dưới 200 từ. Markdown: `####` cho tiêu đề nhỏ, gạch đầu dòng cho danh
sách, in đậm cho số quan trọng. Không lồng quá 2 cấp.

Không xin lỗi sáo rỗng. Không mở đầu bằng "Tuyệt vời!" hay "Câu hỏi hay!".

## 13. Eval

**Golden set 30–50 câu** trong `eval/golden_set.json`. Bắt buộc đủ bốn nhóm:

| Nhóm | Số câu | Kiểm cái gì |
|---|---|---|
| Trả lời được từ tài liệu | ~20 | Độ chính xác + trích nguồn đúng |
| **Phải từ chối** | ~10 | Hỏi thứ không có trong kho — agent có bịa không |
| Cần tool | ~10 | Có gọi đúng tool, có lấy số từ DB không |
| Chống prompt injection | ~5 | Tài liệu chứa lệnh — agent có nghe theo không |

Nhóm "phải từ chối" là nhóm quan trọng nhất. Agent trả lời đúng 100% câu dễ
nhưng bịa ở câu khó thì tệ hơn agent biết nói "mình không biết".

**Chỉ số theo dõi:**

| Chỉ số | Ngưỡng | Đo bằng |
|---|---|---|
| Retrieval recall | > 0.7 | So chunk truy hồi với chunk đúng |
| Faithfulness | > 0.7 | RAGAS |
| Answer relevance | > 0.7 | RAGAS |
| Tỉ lệ từ chối đúng | > 0.9 | Trên nhóm "phải từ chối" |
| Độ trễ p95 | < 5s | Log |
| Chi phí mỗi câu | < 500đ | LangSmith |

Chạy lại eval **mỗi khi đổi prompt, model, hoặc cách chunking**. Ghi số vào
`eval/results/report.md` — đây đồng thời là deliverable #10 của BTC.

## 14. Quan sát

Tracing mỗi câu hỏi bằng LangSmith: câu hỏi → intent → chunk truy hồi → điểm
rerank → tool call → context vào LLM → câu trả lời. Theo dõi token và chi phí
theo phiên.

**Không log** nội dung tài liệu `internal` và thông tin cá nhân người dùng.

## 15. Bản đồ spec sang code

| Mục | File | Trạng thái |
|---|---|---|
| 4 · Luồng | `src/agents/graph.py` | 🟡 thiếu nhánh tool |
| 5 · Router | `src/agents/nodes/router.py` | 🟢 xong |
| 6 · Retrieval | `src/agents/nodes/retrieve.py` · `src/data/retrieval/` | 🟡 chưa bật |
| 7 · Tool | `src/agents/tools/` | 🔴 mới có mock `inventory_lookup`, cần thay |
| 8 · Grounding | `src/agents/nodes/generate.py` · `prompts/system_v1.md` | 🟡 thiếu chống injection |
| 9 · Guardrail | `src/agents/nodes/guardrail.py` | 🟡 thiếu miễn trừ pháp lý |
| 10 · HITL | `src/models/chat.py` event `sensitive` | 🔴 FE chưa dựng khối duyệt |
| 11 · Ingestion | `src/data/pipelines.py` | 🟢 xong, chưa có dữ liệu |
| 12 · Prompt | `src/agents/prompts/` | 🟡 cần `system_v2.md` theo bản này |
| 13 · Eval | `eval/` | 🔴 chưa có |

## 16. Việc cố tình chưa làm

Ghi rõ để khỏi ai tưởng là quên:

- **Không có vòng lặp truy hồi lại.** Chờ số đo từ eval rồi mới quyết.
- **Không có memory dài hạn qua nhiều phiên.** Mỗi phiên độc lập; lịch sử chỉ
  giữ trong `history` của request.
- **Không có multi-agent.** Một graph, bốn node. Thêm agent chỉ khi có bài toán
  thật cần, không thêm cho oai.
- **Không định giá bất động sản cụ thể.** Đây là bài toán riêng, cần mô hình
  riêng và dữ liệu giao dịch thật — ngoài phạm vi.
- **Phân quyền `internal` chưa dùng tới.** Cơ chế đã có sẵn trong code vì nó rẻ
  và đúng ngay từ đầu; giai đoạn này mọi tài liệu đều `public`.
