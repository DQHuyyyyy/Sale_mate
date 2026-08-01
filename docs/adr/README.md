# Architecture Decision Records

Mỗi file ghi lại một quyết định kiến trúc quan trọng: bối cảnh, các lựa chọn đã
cân nhắc, quyết định cuối, và hệ quả.

Viết ADR khi quyết định **khó đảo ngược** hoặc **có đánh đổi thật**. Không cần
ADR cho lựa chọn hiển nhiên.

| # | Quyết định | Trạng thái |
|---|---|---|
| [001](ADR-001-qdrant.md) | Qdrant làm vector store thay vì ChromaDB | Accepted |
| [002](ADR-002-embedding-tieng-viet.md) | OpenAI embedding trước, BGE-M3 sau | Accepted |
| [003](ADR-003-model-routing.md) | Định tuyến model hai tầng | Accepted |
| [004](ADR-004-module-contracts.md) | Tách module bằng Protocol + container | Accepted |

Đổi quyết định thì đánh dấu ADR cũ `Superseded by ADR-XXX` và viết ADR mới,
không sửa đè lên bản cũ.
