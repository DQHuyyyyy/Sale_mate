"""Hạn mức cho hai endpoint CÔNG KHAI và tốn tiền: hỏi đáp và sinh ảnh.

Gộp một chỗ thay vì để mỗi router giữ một bản: hai bên phải cùng một luật, cùng
một giọng văn, và cùng đóng lại khi tắt cờ. Bản trước chép đôi và đã lệch ngay ở
lần sửa đầu tiên — đúng kiểu trôi lệch mà `trang_thai.py` và `dat_coc` đã dính.

**Khách vãng lai đếm theo NGÀY, nhân viên đếm theo 10 PHÚT.** Hai cửa sổ khác
nhau vì chúng chặn hai chuyện khác nhau: với khách đây là trần chi phí (một
người lạ không được đốt quota cả buổi), với nhân viên đây chỉ là phanh chống
vòng lặp retry và tài khoản bị lộ — người thật không gõ nổi 120 câu trong 10
phút, nên trên thực tế nhân viên không có trần.

⚠️ **Câu trả về phải NÓI THẲNG là hết lượt miễn phí, và chỉ đường bằng nút đăng
nhập.** Bản trước cố ý nói vòng — không nhắc quota, chỉ mời liên hệ chuyên viên
tư vấn qua email — với lý do người hỏi tới câu thứ 16 là lead nóng nhất trong
ngày, báo cho họ một bức tường là mất khách. Đợt test 08/09/2026 cho thấy cái giá
của cách nói đó lớn hơn: sale đọc lời mời như một câu trả lời nghiệp vụ, tưởng
trợ lý KHÔNG BIẾT câu trả lời chứ không phải đã hết lượt, và mất niềm tin vào
chất lượng bot. Lời mời còn dẫn tới một hành động sai — gửi email nhờ tư vấn —
trong khi việc đúng cần làm là đăng nhập tài khoản sale.

⚠️ **KHÔNG bao giờ nhúng địa chỉ liên hệ cá nhân vào câu này.** Hằng
`EMAIL_TU_VAN` cũ giữ email cá nhân của một thành viên và nó hiện thẳng ra giao
diện production cho mọi khách vãng lai chạm trần. Cần kênh hỗ trợ thì đó phải là
địa chỉ chính thức của đội, đặt qua biến môi trường, không phải một hằng trong
mã nguồn.

**Khách và nhân viên nhận hai câu khác nhau.** Bảo một người đã đăng nhập đi
đăng nhập là vô nghĩa; trần của nhân viên vốn cũng không phải trần chi phí mà là
phanh chống vòng lặp retry, nên câu của họ nói đúng chuyện đó.

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

MOT_NGAY_GIAY = 86_400.0
MUOI_PHUT_GIAY = 600.0

# Câu chạm trần của NHÂN VIÊN. Cố định vì nó không phụ thuộc endpoint: dù đang
# hỏi đáp hay dựng ảnh, thứ vừa xảy ra đều là "gửi quá nhanh trong ít phút".
#
# Không nói "đăng nhập" ở đây — người đọc câu này đã đăng nhập rồi.
LOI_NHAN_VIEN = (
    "Bạn vừa gửi quá nhiều yêu cầu trong ít phút nên hệ thống tạm dừng để bảo vệ "
    "tài khoản. Chờ khoảng mười phút rồi thử lại nhé."
)


def loi_khach(so_luot: int, don_vi: str) -> str:
    """Câu chạm trần của KHÁCH VÃNG LAI — thông báo hệ thống, không phải câu trả lời.

    Ba thứ phải có, theo đúng thứ tự người đọc cần:

    1. Chuyện gì vừa xảy ra ("đã dùng hết N câu hỏi miễn phí"). Thiếu vế này thì
       sale đọc nó như một câu trả lời nghiệp vụ và tưởng trợ lý bí.
    2. Đây là trần của TÀI KHOẢN KHÁCH, không phải trần của sản phẩm.
    3. Việc cần làm tiếp: đăng nhập. Widget dựng nút từ chính vế này.

    Nêu `so_luot` thay vì viết cứng một con số: hai endpoint có hai trần khác
    nhau (15 câu hỏi, 10 lượt ảnh) và chúng còn đổi được.
    """
    return (
        f"Bạn đã dùng hết {so_luot} {don_vi} miễn phí cho tài khoản khách. "
        "Đăng nhập tài khoản Sale để tiếp tục sử dụng không giới hạn."
    )


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

    `don_vi` là thứ được đếm, ở dạng số nhiều không kèm số ("câu hỏi", "lượt tạo
    ảnh"). Chỉ mình nó khác nhau giữa hai endpoint — phần còn lại của câu chạm
    trần là thông báo hệ thống, phải giống hệt nhau ở mọi chỗ để người dùng nhận
    ra nó bằng mắt mà không cần đọc hết.
    """

    def __init__(self, *, khach_moi_ngay: int, nhan_vien_moi_10_phut: int, don_vi: str) -> None:
        self.khach = RateLimiter(khach_moi_ngay, MOT_NGAY_GIAY)
        self.nhan_vien = RateLimiter(nhan_vien_moi_10_phut, MUOI_PHUT_GIAY)
        self.loi_khach = loi_khach(khach_moi_ngay, don_vi)

    def kiem_tra(self, request: Request, user: CurrentUser | None) -> None:
        """Ghi nhận một lượt. Chạm trần thì raise 429 kèm thông báo hệ thống."""
        if not settings.chat_rate_limit_enabled:
            # Log WARNING vì đây là trạng thái BẤT THƯỜNG: hai endpoint này công
            # khai và mỗi lượt đều gọi model thật, nên quên bật lại trên môi
            # trường công khai là ai có link cũng gọi được không giới hạn.
            logger.warning("Hạn mức đang TẮT — chỉ dùng khi tự test, nhớ bật lại")
            return

        if user is not None:
            con_luot, cho_giay = self.nhan_vien.check(f"user:{user.id}")
            loi = LOI_NHAN_VIEN
        else:
            con_luot, cho_giay = self.khach.check(_khoa_khach(request))
            loi = self.loi_khach

        if con_luot:
            return

        # `Retry-After` giữ đúng ngữ nghĩa HTTP cho máy đọc, nhưng số giây KHÔNG
        # đi vào câu chữ: trần của khách là một ngày, nên "thử lại sau 74.000
        # giây" vừa vô nghĩa với người đọc vừa giấu mất việc cần làm là đăng nhập.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=loi,
            headers={"Retry-After": str(cho_giay)},
        )
