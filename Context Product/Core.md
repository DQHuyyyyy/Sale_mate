# Core.md — Lõi AI Agent

Tài liệu này mô tả phần "trí tuệ" của SalesMate để implement trong `backend/app/agent/`, `ingestion/`, `retrieval/`, `eval/`.

## 1. Agent này là gì (và không phải gì)

SalesMate là **agent có kiểm soát (bounded agent)**, khác chatbot RAG thẳng ở ba điểm:

1. **Quyết định (routing)**: tự chọn nguồn phù hợp cho từng câu hỏi (tài liệu / tồn kho / giá).
2. **Dùng công cụ (tool-use)**: gọi API tồn kho, tra DB giá — lấy dữ liệu ngoài văn bản.
3. **Hành động có hệ quả**: soạn tin gửi khách → vì có hệ quả nên **bắt buộc HITL**.

> Cảnh báo triển khai: đừng cho agent tự do lặp vòng vô tận. Rất nhiều câu chỉ cần **một vòng RAG**. Giá trị agentic nằm ở routing + tool + hành động có duyệt, không phải ở độ phức tạp.

## 2. Luồng orchestrator (query flow)

```
Câu hỏi + vai trò user
   │
   ▼
[1] Router  ── phân loại: tài liệu? tồn kho? giá? hỗn hợp? / hay soạn tin gửi khách?
   │
   ▼
[2] Retrieve (nếu cần tài liệu)
      → Qdrant search, LỌC theo quyền (visibility) NGAY tại truy vấn
      → Re-rank top-k
   │
[3] Tool call (nếu cần)
      → inventory_lookup(project, building, unit_type)   # realtime
      → price_lookup(project, unit_code|unit_type)        # DB có cấu trúc
   │
   ▼
[4] Generate  → LLM sinh câu trả lời, GROUNDING (chỉ dùng context đã truy hồi)
   │           → gắn citation vào từng khẳng định
   ▼
[5] Guardrail
      → nếu độ phủ thấp → trả "chưa đủ dữ liệu" (không suy đoán)
      → phân loại NHẠY CẢM? (giá/cam kết gửi khách) → chặn qua HITL
   │
   ▼
Trả về (stream) + nguồn + (nếu có) thẻ tồn kho + (nếu nhạy cảm) cổng duyệt
```

## 3. Router

- Input: câu hỏi + lịch sử ngắn.
- Output (JSON): `{intent: "doc|inventory|price|mixed|draft_message", needs: [...], filters: {project, building, unit_type}}`.
- Dùng **model rẻ/nhanh** (ví dụ Haiku/GPT-4o-mini) để giảm độ trễ.
- Prompt ép trả JSON thuần; parse an toàn, có fallback về `mixed`.

## 4. Retrieval

- **Embedding**: BGE-M3 hoặc multilingual-e5-large (bắt buộc mạnh tiếng Việt). Cùng model cho ingest và query.
- **Truy hồi**: Qdrant top-k (k≈20) → **re-rank** bằng `bge-reranker-v2-m3` → giữ top-n (n≈5) đưa vào context.
- **Lọc phân quyền TẠI truy vấn**: thêm filter payload `visibility ∈ quyền_của_user` và `is_active = true` vào Qdrant query. Không lọc ở tầng sau. (Xem `Data.md`.)
- **Độ phủ (coverage)**: tính điểm liên quan cao nhất sau rerank; dưới ngưỡng → kích hoạt nhánh "chưa đủ dữ liệu".

## 5. Tool layer

Định nghĩa tool rõ ràng (schema trong `API.md`):

- `inventory_lookup(project, building?, unit_type?, unit_code?)` → trạng thái căn realtime (Còn trống/Giữ chỗ/Đã bán). **Không cache lâu**; nguồn là API/DB tồn kho.
- `price_lookup(project, unit_code? | unit_type?)` → giá từ bảng giá có cấu trúc trong Postgres. **Không lấy giá từ RAG.**

Tool trả dữ liệu có cấu trúc; LLM chỉ diễn giải, không tự chế số.

## 6. Grounding & chống ảo giác

- System prompt ép: **chỉ trả lời dựa trên context được cấp**; nếu context không chứa thông tin → nói chưa đủ dữ liệu.
- Mọi khẳng định từ tài liệu phải kèm **citation** (id tài liệu + phiên bản). FE hiển thị thành chip nguồn.
- Ngưỡng độ phủ thấp → trả thông điệp từ chối chuẩn (xem state ở `Giaodien.md`), kèm gợi ý báo admin bổ sung tài liệu.

## 7. Human-in-the-loop (HITL)

- **Phân loại nhạy cảm**: output được gắn nhãn `sensitive = true` nếu chứa giá cụ thể + ngữ cảnh "gửi/nhắn khách", hoặc cam kết (giữ chỗ, ưu đãi). Dùng luật + model rẻ hỗ trợ.
- **Cổng duyệt**: output nhạy cảm KHÔNG tự gửi. Trả về bản nháp + yêu cầu sale duyệt.
- **Ghi log**: khi sale bấm "Duyệt & gửi", ghi vào `sensitive_actions_log` (ai, nội dung, thời điểm, căn/giá). Đây là bằng chứng kiểm soát.

## 8. Ingestion pipeline (`ingestion/`)

```
Admin upload (PDF / Excel / ảnh)
   → Parse (LlamaParse cho PDF/bảng; giữ cấu trúc bảng → Markdown/JSON)
   → Tách dữ liệu: bảng giá → Postgres có cấu trúc; văn bản → chunk
   → Chunk (tôn trọng cấu trúc, không cắt vỡ bảng)
   → Ảnh mặt bằng: OCR/mô tả + metadata (dự án/tòa/loại căn) để retrieve
   → Embed → Qdrant (kèm metadata + version)
   → Đăng ký vào Postgres: documents + document_versions
```

- **Versioning**: upload bản mới → đánh dấu bản cũ `is_active=false`, `superseded_by`. Truy hồi chỉ lấy `is_active`.
- **Cảnh báo mâu thuẫn** (nâng cao): khi hai tài liệu active mâu thuẫn (ví dụ hai mức chiết khấu), gắn cờ để admin xử lý và cảnh báo trong câu trả lời.

## 9. Chiến lược prompt

- Đặt prompt trong `agent/prompts/*.md`, có version.
- System prompt gồm: vai trò, 7 invariant liên quan (grounding, citation, refusal, không lộ tài liệu nội bộ), format câu trả lời + citation.
- **Model routing**: router & phân loại nhạy cảm dùng model rẻ; câu trả lời cuối dùng model mạnh. Cân bằng độ trễ (mục tiêu < vài giây) và chi phí.
- Bật **prompt caching** và **streaming** để giảm độ trễ cảm nhận.

## 10. Eval (`eval/`)

- **Golden set**: 30–50 cặp câu hỏi/đáp chuẩn do team soạn từ tài liệu thật (gồm cả ca "phải từ chối" và ca phân quyền).
- **Chỉ số**: retrieval recall, faithfulness (bám nguồn), answer relevance, tỉ lệ từ chối đúng, độ trễ p95, chi phí/câu.
- Chạy eval mỗi khi đổi prompt/model/chunking. Không đổi mù — luôn đo trước/sau.
- Có thể dùng RAGAS hoặc tự viết harness gọi LLM chấm faithfulness/relevance.

## 11. Observability

- Tracing mỗi câu hỏi: câu hỏi → chunk truy hồi → điểm rerank → tool call → context vào LLM → câu trả lời. Dùng Langfuse/Phoenix.
- Theo dõi token & chi phí theo phiên.
