"""Schema cho lead đặt cọc — bản chatbot ghi, sale/admin xử lý.

⚠️ Mọi model ở đây chở SỐ ĐIỆN THOẠI và HỌ TÊN của khách thật. Chỉ được trả về
sau `require_sale_hoac_admin`, không bao giờ trên route công khai.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Đúng CHECK constraint của bảng (migration 009). Khai lại ở đây để API trả 422
# với thông điệp đọc được, thay vì để Postgres ném 500 lúc ghi.
TrangThaiLead = Literal["new", "da_goi", "da_coc", "bo", "da_ban"]

# Nhãn tiếng Việt, khớp `src/agents/tools/trang_thai.py` phía lõi AI.
NHAN_LEAD: dict[str, str] = {
    "new": "Mới",
    "da_goi": "Đã gọi",
    "da_coc": "Đã nhận cọc",
    "bo": "Đã huỷ",
    "da_ban": "Đã bán",
}


class DatCocLead(BaseModel):
    id: int
    ma_can: str
    ho_ten: str
    so_dien_thoai: str
    ghi_chu: str
    trang_thai: TrangThaiLead
    created_at: datetime
    # Sale nào tạo lead. Rỗng = khách tự đặt trên portal hoặc qua widget chat,
    # tức khách CHƯA AI NHẬN — đó là thứ đội sale cần nhìn thấy đầu tiên.
    sale_id: int | None = None
    sale_ten: str | None = None
    # Tình trạng căn suy ra từ chính lead này (migration 010) — để sale thấy
    # ngay hệ quả của việc mình đổi trạng thái, không phải mở thêm màn hình.
    tinh_trang_can: str | None = None


class DoiTrangThaiLead(BaseModel):
    trang_thai: TrangThaiLead = Field(
        description=(
            "new = mới · da_goi = đã gọi · da_coc = đã nhận cọc · "
            "bo = huỷ, trả căn về Còn · da_ban = chốt bán, ghi luôn vào sales_history"
        )
    )


class TaoLead(BaseModel):
    """Khách bấm "Đặt cọc" trên trang căn hộ. KHÔNG cần đăng nhập.

    Ràng buộc chặt hơn bảng một chút, vì đây là biên duy nhất người lạ ghi được
    vào bảng chứa thông tin cá nhân.
    """

    ma_can: str = Field(min_length=3, max_length=20)
    ho_ten: str = Field(default="", max_length=100)
    # 0 + 9 chữ số sau khi chuẩn hoá. Cùng luật với `chuan_hoa_sdt` của lõi AI —
    # hai đường vào phải nhận đúng một tập số, nếu không cùng một khách gọi qua
    # chat thì được mà bấm nút thì không.
    so_dien_thoai: str = Field(min_length=9, max_length=20)
    # Chặn ở đây thay vì tin vào TEXT của bảng: ô ghi chú là chỗ duy nhất người
    # lạ nhập được văn bản tự do, và không giới hạn thì nó thành chỗ đổ rác.
    ghi_chu: str = Field(default="", max_length=500)


class KetQuaTaoLead(BaseModel):
    """Trả về SAU khi ghi. Cố ý KHÔNG chở lại số điện thoại.

    Response này đi qua log truy cập, proxy và devtools của trình duyệt. Khách
    vừa tự gõ số đó nên đọc lại cho họ nghe không thêm được gì.
    """

    id: int
    ma_can: str
    loi_nhan: str
