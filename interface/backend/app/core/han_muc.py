"""Hạn mức cho hai endpoint CÔNG KHAI và tốn tiền: hỏi đáp và sinh ảnh.

Gộp một chỗ thay vì để mỗi router giữ một bản: hai bên phải cùng một luật, cùng
một giọng văn, và cùng đóng lại khi tắt cờ. Bản trước chép đôi và đã lệch ngay ở
lần sửa đầu tiên — đúng kiểu trôi lệch mà `trang_thai.py` và `dat_coc` đã dính.

**Khách vãng lai đếm theo NGÀY, nhân viên đếm theo 10 PHÚT.** Hai cửa sổ khác
nhau vì chúng chặn hai chuyện khác nhau: với khách đây là trần chi phí (một
người lạ không được đốt quota cả buổi), với nhân viên đây chỉ là phanh chống
vòng lặp retry và tài khoản bị lộ — người thật không gõ nổi 120 câu trong 10
phút, nên trên thực tế nhân viên không có trần.

⚠️ **Câu trả về KHÔNG được nói "hết lượt".** Người chạm trần là người vừa hỏi 15
câu về căn hộ — lead nóng nhất trong ngày. Báo cho họ một bức tường là mất khách
đúng lúc họ quan tâm nhất; mời họ gặp chuyên viên tư vấn là biến cùng khoảnh
khắc đó thành một đầu mối liên hệ. Đây là quyết định sản phẩm, không phải cách
diễn đạt cho đẹp — đừng đổi lại thành thông báo kỹ thuật.

Hai giới hạn của cơ chế, phải biết trước khi tin vào con số:

- Bộ đếm nằm trong RAM tiến trình. Render free ngủ sau 15 phút không có request,
  và mỗi lần dậy là mọi bộ đếm về 0. Trần theo ngày vì thế là "khoảng 15", không
  phải "đúng 15".
- Khoá của khách là IP. Sau proxy thì `request.client.host` có thể là IP của
  proxy, tức MỌI khách chung một rổ. Xem `_khoa_khach`.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.ratelimit import RateLimiter
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

# Địa chỉ nhận khách từ widget. Để ở BACKEND chứ không phải frontend: câu mời đi
# kèm nó là một quyết định sản phẩm, và bản không stream `/api/chat` cũng phải
# trả về được câu đó cho client không có giao diện.
EMAIL_TU_VAN = "duongquanghuy1072003@gmail.com"

MOT_NGAY_GIAY = 86_400.0
MUOI_PHUT_GIAY = 600.0


def _khoa_khach(request: Request) -> str:
    """Khoá đếm cho khách chưa đăng nhập.

    ⚠️ Sau proxy/CDN, `request.client.host` là IP của proxy chứ không phải của
    khách — lúc đó MỌI khách dùng chung một bộ đếm và người thứ 16 bị mời liên hệ
    dù chưa hỏi câu nào. Kiểm bằng cách mở web từ hai mạng khác nhau (4G và wifi)
    rồi hỏi vượt trần ở máy thứ nhất; máy thứ hai phải vẫn hỏi được.

    Chưa đọc `X-Forwarded-For` ở đây vì tin header do client gửi mà không cấu
    hình danh sách proxy tin cậy là mở đường cho mỗi request khai một IP khác và
    trần thành vô nghĩa. Sửa đúng chỗ là cấu hình uvicorn
    (`--forwarded-allow-ips`), không phải đọc tay trong hàm này.
    """
    return f"ip:{request.client.host}" if request.client else "ip:unknown"


class HanMuc:
    """Một bộ hạn mức cho một endpoint.

    `loi_moi` là câu trả về khi chạm trần — mỗi endpoint một câu, vì mời khách
    liên hệ về việc bố trí nội thất khác với mời họ trao đổi về căn hộ.
    """

    def __init__(self, *, khach_moi_ngay: int, nhan_vien_moi_10_phut: int, loi_moi: str) -> None:
        self.khach = RateLimiter(khach_moi_ngay, MOT_NGAY_GIAY)
        self.nhan_vien = RateLimiter(nhan_vien_moi_10_phut, MUOI_PHUT_GIAY)
        self.loi_moi = loi_moi

    def kiem_tra(self, request: Request, user: CurrentUser | None) -> None:
        """Ghi nhận một lượt. Chạm trần thì raise 429 kèm lời mời liên hệ."""
        if not settings.chat_rate_limit_enabled:
            # Log WARNING vì đây là trạng thái BẤT THƯỜNG: hai endpoint này công
            # khai và mỗi lượt đều gọi model thật, nên quên bật lại trên môi
            # trường công khai là ai có link cũng gọi được không giới hạn.
            logger.warning("Hạn mức đang TẮT — chỉ dùng khi tự test, nhớ bật lại")
            return

        if user is not None:
            con_luot, cho_giay = self.nhan_vien.check(f"user:{user.id}")
        else:
            con_luot, cho_giay = self.khach.check(_khoa_khach(request))

        if con_luot:
            return

        # `Retry-After` giữ đúng ngữ nghĩa HTTP cho máy đọc, nhưng số giây KHÔNG
        # đi vào câu chữ: "thử lại sau 74.000 giây" chính là cách nói "hết lượt"
        # mà mục trên vừa cấm.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=self.loi_moi,
            headers={"Retry-After": str(cho_giay)},
        )
