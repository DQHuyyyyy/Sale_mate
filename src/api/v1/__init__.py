"""Gom router phiên bản v1.

Thêm nhóm endpoint mới = tạo file trong thư mục này rồi include_router bên dưới.

Lõi AI chỉ phục vụ hai việc: health check và chat. Dữ liệu căn hộ do
`interface/backend` (cổng 8000) lo — nó đọc thẳng Supabase.

`chat` và `documents` nằm sau khoá dịch vụ (`src/api/bao_ve.py`); `health` thì
KHÔNG — Render gọi `healthCheckPath` mà không cầm khoá nào, chặn nó là service
bị đánh dấu hỏng rồi khởi động lại vòng quanh. Đổi lại, mọi thứ `/health` trả về
đều phải coi là công khai; nó vốn đã chỉ trả tên cấu hình và cờ có/không.
"""

from fastapi import APIRouter

from src.api.bao_ve import BAO_VE
from src.api.v1 import chat, documents, health

router = APIRouter()
router.include_router(health.router)
router.include_router(chat.router, dependencies=BAO_VE)
# Tài liệu cũng phải khoá: đây là hồ sơ NỘI BỘ, và `/api/tai-lieu` bên portal
# bắt đăng nhập đúng vì lý do đó. Để hở ở tầng này là cái chặn kia thành trang
# trí — gọi thẳng lõi AI là đọc được toàn văn mà không cần tài khoản nào.
router.include_router(documents.router, dependencies=BAO_VE)

__all__ = ["router"]
