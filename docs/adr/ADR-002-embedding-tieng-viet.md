# ADR-002: Embedding cho tiếng Việt — OpenAI trước, BGE-M3 sau

**Ngày:** 2026-08-01
**Trạng thái:** Accepted

## Bối cảnh

Toàn bộ tài liệu và câu hỏi của người dùng đều bằng tiếng Việt. Chất lượng
embedding quyết định trực tiếp việc truy hồi có lấy đúng đoạn văn bản hay không
— retrieval sai thì mọi thứ phía sau (rerank, grounding, trích nguồn) đều vô
nghĩa.

Tiếng Việt có dấu và nhiều từ ghép; các model embedding chỉ huấn luyện tốt cho
tiếng Anh thường cho kết quả kém rõ rệt.

## Các lựa chọn

### 1. BGE-M3 chạy local
- **Ưu:** đa ngôn ngữ, mạnh tiếng Việt; miễn phí sau khi tải; dữ liệu không rời
  máy.
- **Nhược:** kéo theo `torch` + `sentence-transformers` ≈ 2GB. Điều này làm Docker
  image phình rất to, CI chậm hẳn, và Render free tier (512MB RAM) **không chạy nổi**.

### 2. `text-embedding-3-small` của OpenAI
- **Ưu:** không thêm dependency nào; đã có sẵn API key; đa ngôn ngữ khá tốt;
  rẻ (~$0.02 / 1M token).
- **Nhược:** tốn tiền theo lượt gọi; phụ thuộc mạng; kém BGE-M3 ở tiếng Việt.

### 3. `multilingual-e5-large`
- Cùng đánh đổi như BGE-M3, chất lượng tiếng Việt tương đương.

## Quyết định

**Giai đoạn hiện tại dùng `text-embedding-3-small` của OpenAI.** BGE-M3 để trong
`requirements-ml.txt` (đang comment), bật khi có nhu cầu thật.

## Lý do

1. `torch` 2GB trong `requirements.txt` sẽ làm hỏng hai deliverable của BTC cùng
   lúc: DevOps (Docker image quá lớn, CI chậm) và Live URL (Render free tier
   không đủ RAM).
2. Ở quy mô demo (vài chục tài liệu), khoảng cách chất lượng giữa OpenAI và
   BGE-M3 chưa đủ lớn để đánh đổi hai deliverable trên.
3. Đây là quyết định **có thể đảo ngược rẻ**: `Embedder` là Protocol, thêm
   `BGEEmbedder` rồi đổi một dòng ở `src/bootstrap.py`.

## Hệ quả

- Phải đo lại: khi eval có golden set, so điểm retrieval recall giữa hai
  embedder rồi mới quyết định chính thức. Không đổi mù.
- **Bắt buộc:** ingest và query phải dùng **cùng một** embedder. Đổi embedder là
  phải re-index toàn bộ, vì vector cũ không so sánh được với vector mới.
- `FakeEmbedder` (hash, không gọi mạng) dùng cho test để CI không tốn tiền và
  không phụ thuộc mạng.
