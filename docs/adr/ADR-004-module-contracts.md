# ADR-004: Tách module bằng Protocol và dependency container

**Ngày:** 2026-08-01
**Trạng thái:** Accepted

## Bối cảnh

Team bốn người (`huy`, `dat`, `viet`, `phuc`) làm song song trên cùng repo trong
sáu tuần. Ba mảng công việc phụ thuộc lẫn nhau:

- **Data** cần thời gian dựng Qdrant, parse tài liệu, ingest.
- **AI_core** cần Data để truy hồi.
- **Interface** cần AI_core để trả lời.

Nếu để phụ thuộc trực tiếp, người sau phải chờ người trước xong mới bắt đầu
được — sáu tuần không đủ. Rủi ro thứ hai: bốn người cùng sửa vài file dùng chung
sẽ conflict liên tục.

## Các lựa chọn

1. **Import trực tiếp giữa các module.** Đơn giản, nhưng ai cũng phải chờ, và
   đổi một class là vỡ cả hai module khác.
2. **Protocol + dependency container.** Mỗi module công bố `contracts.py` chỉ
   gồm Protocol và DTO. Module khác import đúng file đó. Việc gắn Protocol với
   class thật nằm ở một chỗ duy nhất.
3. **Tách thành nhiều repo/service.** Cách ly triệt để nhất, nhưng chi phí vận
   hành quá lớn cho một dự án sáu tuần.

## Quyết định

Chọn phương án 2.

```
src/
├── core/         config · logging · exceptions · container   (dùng chung)
├── models/       DTO — HỢP ĐỒNG FE ↔ BE                      (đóng băng)
├── data/         ĐƯỜNG GHI: crawl → parse → chunk → embed → store   → viet
├── rag/          ĐƯỜNG ĐỌC: retriever · rerankers · grounding       → phuc
├── agents/       ĐIỀU PHỐI: graph · nodes · tools                   → huy
├── eval/         Đo lường trên bộ câu hỏi vàng                      → phuc
├── api/          deps · errors · v1/                                → huy
├── services/     adapter ra ngoài (OpenAI)
├── cli.py        dòng lệnh: ingest · search · eval
└── bootstrap.py  NƠI DUY NHẤT gắn Protocol ↔ implementation
```

**Quy tắc:** module chỉ được import `contracts.py` và `models/` của module khác,
không bao giờ import class cụ thể.

**Phụ thuộc một chiều `rag → data`.** `data/` tuyệt đối không import `rag/`.
Vì thế `RetrievalFilter` nằm ở `data/contracts.py` — nó là tham số của
`VectorStore.search()`; để bên `rag/` là tạo vòng lặp import.

### Cập nhật 2026-08-08 — vì sao tách `rag/` khỏi `data/`

Ban đầu truy hồi nằm trong `src/data/retrieval/`. Cách chia đó cắt ngang công
việc của một người: Phúc phải ghi vào cả `data/` (truy hồi) lẫn `agents/`
(grounding trong `generate.py`), nên **không ai sở hữu "RAG từ đầu đến cuối"**.

Hậu quả thật: Viet nạp 870 chunk vào Qdrant Cloud, Phúc xây xong pipeline RAG,
nhưng `bootstrap.py` vẫn trỏ `InMemoryVectorStore` với `ENABLE_RAG = False`.
Web app đứt khỏi dữ liệu nhiều ngày mà không ai phát hiện — Phúc tưởng xong,
Huy không biết cần bật, và khoảng giữa không thuộc trách nhiệm của ai.

Cách chia mới theo **đường ghi / đường đọc / điều phối** khớp cả với năng lực
lẫn người phụ trách, và sau đó không file nào có hai chủ.

## Lý do

1. **Không ai phải chờ ai.** Mỗi Protocol có sẵn một cài đặt giả lập chạy được
   ngay: `InMemoryVectorStore`, `FakeEmbedder`, `ScriptedProvider`,
   `EmptyRetriever`, `InMemoryPortalRepository`. AI_core code và test được từ
   giờ đầu dù Data chưa có dữ liệu thật.
2. **Conflict gần như bằng không.** Mỗi người sở hữu một thư mục riêng.
3. **Test rẻ.** `container.override(...)` thay dịch vụ trong một dòng, không cần
   monkeypatch rải rác — nhờ đó đạt 81% coverage mà không test nào gọi mạng.
4. **Quyết định công nghệ đảo ngược được rẻ.** Đổi Qdrant, đổi embedder, đổi LLM
   provider đều là sửa một dòng ở `bootstrap.py`.

## Hệ quả

- `src/models/` và các `contracts.py` **bị đóng băng**: muốn sửa phải mở PR
  riêng vào `develop` cho cả team review, không lẫn vào PR tính năng. Đây là cái
  giá phải trả để đổi lấy việc bốn người chạy song song.
- Thêm một tầng gián tiếp: đọc code phải mở `bootstrap.py` mới biết Protocol nào
  đang chạy bằng class nào. Chấp nhận được vì chỉ có đúng một file cần đọc.
- `interface/frontend/src/lib/types.ts` là nửa FE của hợp đồng. Đổi `src/models/` mà quên
  đổi file này thì FE và BE lệch nhau lặng lẽ — CI không bắt được, phải nhớ.
