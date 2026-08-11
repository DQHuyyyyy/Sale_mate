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
├── services/     adapter ra ngoài: llm.py · portal.py
├── bootstrap.py  🔑 NƠI DUY NHẤT gắn Protocol ↔ implementation
└── main.py
interface/        FE + API sản phẩm, gộp một chỗ cho dễ quản lý
├── frontend/     Next.js — portal + AIWidget                   → huy
└── backend/      API sản phẩm :8000, gọi lõi AI qua AI_CORE_URL
```

**Quy tắc bắt buộc:**

- Module chỉ import `contracts.py` và `models/` của module khác.
  **Không bao giờ** import class cụ thể (`QdrantVectorStore`, `OpenAIProvider`…).
- `src/models/` và mọi `contracts.py` **đóng băng**. Muốn sửa → PR riêng vào
  `develop`, cả team review, không lẫn vào PR tính năng.
- Sửa `src/models/` thì phải sửa `interface/frontend/src/lib/types.ts` trong
  **cùng một PR**.

Lý do: [ADR-004](docs/adr/ADR-004-module-contracts.md).

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
python -m src.cli ingest --all      # nạp 4 nguồn
python -m src.cli search "câu hỏi"  # thử truy hồi
python -m src.cli eval retrieval    # đo trên bộ câu hỏi vàng
```

Thêm nguồn mới: viết hàm `ingest_<tên>()` trong `src/data/ingest/sources.py`
rồi thêm một dòng vào `SOURCES`. **Không tạo script rời** — bài học cũ: bốn
script tự dựng `QdrantVectorStore` riêng nên chạy tốt, trong khi `bootstrap.py`
vẫn dùng in-memory, web app đứt khỏi dữ liệu nhiều ngày mà không ai phát hiện.

## Luồng agent

```
START → router → tools ─┬─(cần tài liệu)→ retrieve → generate → guardrail → END
                        └─(không cần)──────────────→ generate → guardrail → END
```

- `router` — luật từ khoá trước, model rẻ sau. Nhãn lạ thì fallback `general`.
- `tools` — chạy tool khai là phục vụ nhãn hiện tại. Nằm trên đường đi chung và
  tự thoát khi không có tool nào nhận, nên thêm tool không phải sửa `graph.py`.
- `retrieve` — chỉ gọi `Retriever` Protocol, không biết gì về Qdrant.
- `generate` — model mạnh; có context thì ép grounding. Số liệu tool đứng
  **trước** tài liệu trong prompt: tool đọc nguồn sự thật lúc hỏi, vector store
  chỉ là bản chụp.
- `guardrail` — độ phủ thấp → trả "chưa đủ dữ liệu"; gắn cờ nhạy cảm; gộp nguồn
  tài liệu với nguồn tool. Có kết quả tool thì **không** từ chối dù độ phủ 0.

Thêm node: kế thừa `BaseNode`, chỉ viết `execute()` — try/except, log, đo thời
gian đã có sẵn ở lớp cha. Node **không** trả khoá `metadata`, lớp cha đang dùng
khoá đó để gắn thời gian chạy.

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

## Lệnh

```bash
make run        # backend  http://localhost:8000/docs
make fe         # frontend http://localhost:3000
make infra      # Qdrant + Postgres
make check      # lint + format + test — CHẠY TRƯỚC KHI PUSH
make cov        # test + coverage (gate 60%)
```

## Quy ước code

**Python** — Python 3.11, type hint đầy đủ, hàm ≤30 dòng, không `except:` trần,
không hardcode secret. Lỗi nghiệp vụ raise lớp trong `src/core/exceptions.py`,
**không** raise `HTTPException` ngoài tầng `api/`.

**TypeScript** — strict mode, component nhỏ, gọi API qua `src/lib/`.

**Giao diện** — tiếng Việt, câu chủ động, sentence case. Màu/bo góc/font lấy từ
token trong `interface/frontend/src/app/globals.css`, không hardcode trong
component.

**Thông điệp lỗi** — nói rõ chuyện gì và cách khắc phục. Không xin lỗi sáo rỗng,
không lộ stack trace ra ngoài.

**Test** — không test nào được gọi OpenAI hay Qdrant thật. Dùng `FakeEmbedder`,
`ScriptedProvider`, `InMemoryVectorStore`, hoặc `container.override(...)`.

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
