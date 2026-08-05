# ADR-001: Dùng Qdrant làm vector store thay vì ChromaDB

**Ngày:** 2026-08-01
**Trạng thái:** Accepted

## Bối cảnh

Hệ thống cần lưu embedding của tài liệu bất động sản (chính sách, bảng giá,
tiện ích, pháp lý) để trả lời câu hỏi có trích nguồn.

Ràng buộc quyết định: tài liệu có hai mức hiển thị — **công khai** và **nội bộ**.
Người dùng không có quyền tuyệt đối không được thấy nội dung nội bộ, kể cả gián
tiếp qua câu trả lời của LLM. Ngoài ra tài liệu có **phiên bản**: khi upload bản
mới, bản cũ phải ngừng được truy hồi.

Nghĩa là việc lọc phải xảy ra **ngay trong truy vấn vector**, không phải lọc kết
quả sau khi đã lấy về. Lọc sau là sai về bảo mật (nội dung đã vào context của
LLM) và sai về chất lượng (top-k bị chiếm chỗ bởi chunk không được phép đọc).

## Các lựa chọn

### 1. ChromaDB — mặc định của template BTC
- **Ưu:** cài đặt đơn giản nhất, chạy in-process, template đã có sẵn cấu hình.
- **Nhược:** metadata filtering có nhưng yếu hơn; ít tài liệu về hành vi khi kết
  hợp nhiều điều kiện lọc với ANN search; khó kiểm soát chính xác thứ tự
  filter-then-search.

### 2. Qdrant
- **Ưu:** payload filtering là tính năng hạng nhất, có payload index riêng cho
  từng trường; filter được áp trong lúc duyệt HNSW nên vừa đúng vừa nhanh;
  self-host bằng một container; Qdrant Cloud có free tier ~1GB không cần thẻ.
- **Nhược:** thêm một service phải chạy; team phải học thêm một API.

### 3. pgvector trong PostgreSQL
- **Ưu:** một database cho cả dữ liệu quan hệ lẫn vector; lọc bằng SQL `WHERE`
  nên rất tự nhiên.
- **Nhược:** hiệu năng ANN kém hơn ở quy mô lớn; phải tự quản lý index; ít công
  cụ quan sát chuyên cho vector.

## Quyết định

Chọn **Qdrant**.

## Lý do

1. Yêu cầu phân quyền là ràng buộc cứng của sản phẩm, không phải tính năng phụ.
   Qdrant là lựa chọn duy nhất trong ba cái mà việc lọc `visibility` +
   `is_active` tại truy vấn vừa đúng ngữ nghĩa vừa được index hỗ trợ.
2. Versioning tài liệu dùng chung cơ chế đó: `is_active=false` cho bản cũ là đủ,
   không cần xoá dữ liệu.
3. Free tier đủ cho quy mô demo, không phát sinh chi phí.

## Hệ quả

- Thêm một container vào `docker-compose.yml`; dev phải chạy `make infra`.
- Để không chặn ai khi chưa có Docker, hệ thống có **hai** cài đặt `VectorStore`:
  `InMemoryVectorStore` (mặc định, dev/test) và `QdrantVectorStore` (staging/prod).
  Cả hai áp **cùng một bộ lọc** để hành vi không lệch nhau — xem
  `tests/test_data/test_retrieval.py`.
- Đổi sang Chroma hay pgvector sau này chỉ sửa một dòng ở `src/bootstrap.py`, vì
  mọi bên gọi chỉ phụ thuộc `VectorStore` Protocol trong `src/data/contracts.py`.
