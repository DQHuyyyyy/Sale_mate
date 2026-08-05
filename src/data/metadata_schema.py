"""Cấu trúc dữ liệu chung (metadata schema) cho mọi nguồn RAG.

`LoadedDocument.metadata` / `Chunk.metadata` là `dict[str, Any]` tự do —
`contracts.py` đóng băng nên không ép kiểu ở đó được. File này định nghĩa quy
ước chung mà MỌI nguồn (tồn kho, batdongsan, meeyland, ...) phải tuân theo, để
lọc phân quyền, lọc theo dự án và trích nguồn hoạt động nhất quán dù dữ liệu
đến từ nội bộ hay crawl.

Thêm nguồn mới → gọi `validate_metadata()` trên từng `LoadedDocument` trước
khi ingest (script ingest hoặc test) để phát hiện thiếu khoá ngay, không phải
khi đã lên Qdrant mới biết.

Quản lý phiên bản (mục 6 Data Handling) — phạm vi hiện tại:
- ĐÃ LÀM: `version` = ngày crawl/ingest, gán vào `Chunk.version` (contracts.py
  đã định nghĩa field này từ trước nhưng chưa nguồn nào set).
- ĐÃ LÀM: trạng thái active/expired thật — `QdrantVectorStore.list_active_doc_ids()`
  + `.mark_inactive()` (2 method mở rộng ngoài `VectorStore` Protocol, chỉ
  dùng nội bộ trong scripts ingest) so lần crawl mới với dữ liệu đang active,
  tin nào đã bị gỡ khỏi site thì đánh `is_active=False` — giữ nguyên text cũ
  (không xoá) nên coi như một dạng lịch sử tối thiểu cho các tin đã hết hiệu
  lực. Xem `scripts/ingest_more_sources.py`.
- CHƯA LÀM (rủi ro cao nếu làm vội, cố tình không tự sửa):
  1. Không giữ lịch sử NHIỀU phiên bản của CÙNG một tin còn hiệu lực — nếu
     tin vẫn còn trên site nhưng giá/nội dung đổi, re-ingest vẫn ghi đè theo
     chunk id cố định, mất bản cũ. Muốn giữ cần đổi cách đặt chunk id (vd
     thêm version vào id) — ảnh hưởng cách retrieval trả kết quả (có thể trả
     về nhiều bản cũ/mới của cùng 1 căn), cần bàn với team trước khi đổi.
  2. Không cảnh báo khi 2 nguồn (batdongsan vs meeyland) cùng mô tả một căn
     nhưng giá/thông tin lệch nhau — cần thuật toán khớp theo địa chỉ/đặc
     điểm vì không có mã căn chung giữa 2 site của bên thứ ba; ghép sai sẽ tạo
     ra một "mâu thuẫn" giả — vi phạm chính nguyên tắc "không bịa" mà việc
     này định phục vụ, nên chưa làm cho tới khi có cách khớp đủ tin cậy.
"""

from __future__ import annotations

REQUIRED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "visibility",  # "public" | "internal" — phân quyền lọc tại tầng truy hồi
        "section",  # nhóm hiển thị/trích nguồn, vd "Vinhomes Ocean Park Gia Lâm"
        "project",  # dự án/toà nhà cụ thể nếu biết (vd "R103"), fallback tên khu đô thị
        "source_site",  # nguồn gốc: "noi-bo" hoặc domain đã crawl, vd "meeyland.com"
        "image_urls",  # list[str] — URL ảnh công khai; [] nếu chưa có hạ tầng phục vụ ảnh
        "version",  # ISO date lấy/crawl dữ liệu — Chunk.version đọc thẳng khoá này
    }
)


def validate_metadata(metadata: dict, *, doc_id: str) -> None:
    """Chặn sớm nguồn dữ liệu mới thiếu khoá metadata bắt buộc.

    Không kiểm tra kiểu giá trị (contracts.py không ép), chỉ kiểm tra có mặt —
    đủ để tránh lỗi "None" âm thầm khi lọc theo project/visibility ở Qdrant.
    """
    missing = REQUIRED_METADATA_KEYS - metadata.keys()
    if missing:
        raise ValueError(f"Tài liệu '{doc_id}' thiếu metadata bắt buộc: {sorted(missing)}")
