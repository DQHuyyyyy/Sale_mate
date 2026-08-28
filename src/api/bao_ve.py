"""Chốt chặn của lõi AI: xác thực dịch vụ + phanh chi phí.

Vì sao cần: `render.yaml` khai lõi AI là `type: web`, nên Render cấp cho nó một
URL công khai trên Internet. Trước file này, `/api/v1/chat` không có `Depends`
nào — ai biết URL đều gọi thẳng được, **bỏ qua toàn bộ tầng bảo vệ của API sản
phẩm**: hạn mức theo IP/tài khoản ở `app/core/han_muc.py`, và cả phân quyền của
`/api/tai-lieu`. Mà chỗ tốn tiền là lõi AI, không phải tầng trên.

Private service (`type: pserv`) là cách sạch hơn — Render không cấp URL công
khai cho nó — nhưng gói free không có loại service đó. Nên đường đi ở đây là
khoá dùng chung giữa hai service.

## Hai chốt, hai việc khác nhau

`xac_thuc_dich_vu`   ai được gọi          → 401
`phanh_chi_phi`      gọi được bao nhiêu   → 429

Chốt thứ hai KHÔNG thừa khi đã có chốt thứ nhất. Khoá lộ ra (log, biến môi
trường của một máy dev, mirror repo) thì chốt thứ nhất im lặng mở toang, và dấu
hiệu duy nhất là hoá đơn OpenAI. Phanh chi phí là thứ vẫn giữ được trần trong
lúc đó.

## Phanh chi phí đếm TOÀN TIẾN TRÌNH, không đếm theo IP

Cố tình khác `han_muc.py` bên portal. Ở đây người gọi hợp lệ duy nhất là API sản
phẩm, tức MỌI request đến từ một IP — đếm theo IP thì hoặc trần rơi đúng vào lưu
lượng thật, hoặc phải nới rộng tới mức vô nghĩa. Cái cần chặn ở tầng này là tổng
chi tiêu chạy loạn, nên bộ đếm là một rổ chung.

Công bằng giữa người dùng vẫn là việc của portal — đó là nơi có danh tính để mà
công bằng. Hai tầng chặn hai chuyện khác nhau, không tầng nào thay được tầng kia.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.core.ratelimit import RateLimiter

logger = get_logger(__name__)

# Tên header. `X-API-Key` chứ không phải `Authorization: Bearer`: đây là danh
# tính của một DỊCH VỤ, không phải của một người, và trộn chung một header với
# JWT người dùng là mời người sau nhầm hai thứ đó là một.
TEN_HEADER = "X-API-Key"

# Một rổ chung cho cả tiến trình — xem chú thích đầu file.
_KHOA_CHUNG = "toan-tien-trinh"
_MOT_PHUT = 60.0

# Dựng theo cấu hình ở lần gọi đầu. Không dựng sẵn ở cấp module vì `Settings`
# đọc `.env` lúc import, mà test cần đổi trần rồi chạy lại.
_phanh: RateLimiter | None = None
_tran_dang_dung: int | None = None


def _lay_phanh(tran_moi_phut: int) -> RateLimiter:
    global _phanh, _tran_dang_dung
    if _phanh is None or _tran_dang_dung != tran_moi_phut:
        _phanh = RateLimiter(tran_moi_phut, _MOT_PHUT)
        _tran_dang_dung = tran_moi_phut
    return _phanh


def dat_lai_phanh() -> None:
    """Xoá bộ đếm. Chỉ dùng trong test — mỗi ca phải khởi đầu như nhau."""
    global _phanh, _tran_dang_dung
    _phanh = None
    _tran_dang_dung = None


_LOI_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail=f"Thiếu hoặc sai khoá dịch vụ. Gửi kèm header {TEN_HEADER}.",
    headers={"WWW-Authenticate": "ApiKey"},
)


def xac_thuc_dich_vu(
    x_api_key: str | None = Header(default=None, alias=TEN_HEADER),
    settings: Settings = Depends(get_settings),
) -> None:
    """Chỉ dịch vụ cầm khoá dùng chung mới gọi được.

    Khoá RỖNG xử lý theo môi trường, và đây là chỗ dễ chọn sai nhất:

    - `production` — **chặn hết**. Cổng bảo vệ mà thất bại theo hướng MỞ thì nó
      không phải cổng: quên khai biến trên Render là quay lại đúng trạng thái
      đang bị báo lỗi, mà lần này còn có một file tên `bao_ve.py` trong repo làm
      người đọc yên tâm. Cổng chính sách ngày 26/08/2026 đã hỏng đúng kiểu đó —
      ngừng bảo vệ hoàn toàn trong im lặng vì hết hạn mức nhà cung cấp.
    - còn lại — cho qua kèm WARNING. `make run-ai` rồi mở `/docs` bấm thử phải
      chạy được, không thì mọi người sẽ tự tắt cổng đi cho đỡ vướng.

    So sánh bằng `compare_digest` chứ không bằng `==`: thời gian so chuỗi rò rỉ
    số ký tự đầu khớp, và endpoint này công khai nên đo được từ xa.
    """
    khoa_that = settings.ai_core_api_key
    if not khoa_that:
        if settings.is_production:
            logger.error(
                "AI_CORE_API_KEY chưa đặt trên production — lõi AI đang từ chối MỌI request. "
                "Đặt biến này ở cả hai service (lõi AI và API sản phẩm) rồi deploy lại."
            )
            raise _LOI_401
        logger.warning(
            "AI_CORE_API_KEY chưa đặt — lõi AI đang mở cho mọi người gọi. "
            "Chỉ chấp nhận được ở máy dev; trên môi trường có người ngoài truy cập thì PHẢI đặt."
        )
        return

    if not x_api_key or not hmac.compare_digest(x_api_key, khoa_that):
        raise _LOI_401


def phanh_chi_phi(settings: Settings = Depends(get_settings)) -> None:
    """Trần số lượt cho CẢ tiến trình. 0 = tắt.

    Đây là phanh tay, không phải hạn mức người dùng: đặt cao hơn hẳn lưu lượng
    thật để nó chỉ bắt lúc có gì đó chạy loạn — vòng lặp retry của client, khoá
    bị lộ, hoặc một script quét. Đặt sát lưu lượng thật là tự chặn khách của mình.

    Trần này KHÔNG thay được trần chi tiêu ở console OpenAI. Đó mới là phanh duy
    nhất không lách được; cái ở đây chỉ chặn sớm hơn và rẻ hơn.
    """
    tran = settings.ai_core_rate_limit_per_minute
    if tran <= 0:
        return

    con_luot, cho_giay = _lay_phanh(tran).check(_KHOA_CHUNG)
    if con_luot:
        return

    logger.warning("Lõi AI chạm trần %s lượt/phút — có thể đang bị gọi loạn", tran)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Trợ lý đang quá tải. Đợi một chút rồi hỏi lại nhé.",
        headers={"Retry-After": str(cho_giay)},
    )


# Gắn vào router bằng `dependencies=[...]`, không phải tham số của hàm xử lý:
# hai chốt này không trả về gì cho hàm dùng, và khai ở cấp router thì endpoint
# mới thêm vào cũng tự được che — quên gắn là quên đúng thứ đang bảo vệ mình.
BAO_VE = [Depends(xac_thuc_dich_vu), Depends(phanh_chi_phi)]
