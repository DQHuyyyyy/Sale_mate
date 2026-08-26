"""Sửa ảnh nội thất bằng AI — tính năng "Modify Object".

Người dùng đang xem một ảnh của căn, gõ "đổi sofa thành màu nâu", hệ thống lấy
đúng ảnh đó làm gốc rồi sinh ảnh mới.

**Ảnh sinh ra KHÔNG được lưu.** Nó chỉ đi về phiên chat đang mở rồi biến mất.
Lý do không phải kỹ thuật mà là trung thực: đây là ảnh minh hoạ do AI tạo cho
một tài sản đang rao bán thật. Lưu nó cạnh ảnh thật trong `apartment_images` thì
khách khác vào xem sẽ tưởng căn đó có bộ sofa nâu — quảng cáo sai sự thật, dù
không ai cố ý. Tầng giao diện còn dán nhãn "Ảnh minh hoạ do AI tạo" lên ảnh.

Ảnh gốc CHỈ được lấy từ bảng `apartment_images` theo đúng mã căn client gửi
lên, không bao giờ nhận URL thẳng từ client — nhận URL là mở đường cho người lạ
bắt server tải về bất cứ thứ gì (SSRF).
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.db import fetch_one

logger = logging.getLogger(__name__)

_API_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_API_OPENAI = "https://api.openai.com/v1/images/edits"
_API_SEEDREAM = "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"

# Ảnh gốc nằm ở Google Drive (link thumbnail công khai). Drive từ chối request
# không có User-Agent trình duyệt.
_UA = "Mozilla/5.0 (compatible; SalesMate/1.0)"

# Trần kích thước ảnh gốc. Ảnh quá lớn vừa tốn token vừa dễ chạm timeout.
_TRAN_ANH_BYTE = 8 * 1024 * 1024

_HUONG_DAN = (
    "Bạn đang chỉnh sửa ảnh nội thất của một căn hộ có thật.\n"
    "Yêu cầu của khách: {yeu_cau}\n\n"
    "Chỉ thay đổi đúng thứ khách nêu. Giữ nguyên bố cục phòng, góc chụp, ánh sáng, "
    "kích thước ảnh và mọi đồ vật khác. Không thêm chữ, watermark hay logo vào ảnh."
)


class ImageEditError(Exception):
    """Lỗi nghiệp vụ — router đổi thành HTTP, thông điệp hiện thẳng cho người dùng."""


def _anh_cua_can(ma_can: str, image_id: int) -> str:
    """URL ảnh gốc, chỉ khi ảnh đó THẬT SỰ thuộc căn được nêu.

    Ràng cả `ma_can` lẫn `id` có chủ đích: thiếu vế đầu thì ai cũng đọc được ảnh
    của mọi căn bằng cách dò id.
    """
    row = fetch_one(
        "SELECT image_url FROM apartment_images WHERE id = %s AND ma_can = %s",
        (image_id, ma_can),
    )
    if not row or not row.get("image_url"):
        raise ImageEditError("Không tìm thấy ảnh này trong căn đang xem. Bạn chọn lại ảnh giúp mình nhé.")
    return str(row["image_url"])


async def _tai_anh(url: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _UA})
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("Không tải được ảnh gốc: %s", url)
        raise ImageEditError("Không tải được ảnh gốc của căn. Thử lại sau ít phút.") from exc

    if len(response.content) > _TRAN_ANH_BYTE:
        raise ImageEditError("Ảnh gốc quá lớn để xử lý.")

    mime = (response.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
    if not mime.startswith("image/"):
        raise ImageEditError("Đường dẫn ảnh của căn không trả về ảnh.")
    return response.content, mime


def _doc_anh_tra_ve(data: dict[str, Any]) -> tuple[bytes, str]:
    """Rút ảnh khỏi phản hồi Gemini.

    API trả khoá theo camelCase (`inlineData`) nhưng tài liệu dùng snake_case —
    đọc cả hai để không phụ thuộc vào việc Google giữ nguyên kiểu đặt tên.
    """
    ung_vien = data.get("candidates") or []
    if not ung_vien:
        raise ImageEditError("Gemini không trả về ảnh nào. Bạn thử mô tả lại yêu cầu cụ thể hơn nhé.")

    ly_do = ung_vien[0].get("finishReason")
    parts = (ung_vien[0].get("content") or {}).get("parts") or []
    for part in parts:
        khoi = part.get("inlineData") or part.get("inline_data")
        if khoi and khoi.get("data"):
            mime = khoi.get("mimeType") or khoi.get("mime_type") or "image/png"
            return base64.b64decode(khoi["data"]), mime

    # Model nhiều khi trả CHỮ giải thích vì sao nó không sửa — hiện nguyên văn
    # còn hữu ích hơn một câu lỗi chung chung.
    chu = " ".join(p["text"] for p in parts if p.get("text")).strip()
    if chu:
        raise ImageEditError(f"Chưa sửa được ảnh: {chu[:300]}")
    raise ImageEditError(f"Gemini không trả về ảnh (finishReason={ly_do}). Bạn thử mô tả lại yêu cầu nhé.")


_TEN_KEY = {"openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY", "seedream": "ARK_API_KEY"}
_TEN_MODEL = {"openai": "OPENAI_IMAGE_MODEL", "gemini": "GEMINI_IMAGE_MODEL", "seedream": "SEEDREAM_MODEL"}


def _loi_tu_status(status: int, than: str) -> str:
    ten_key = _TEN_KEY.get(settings.image_provider, "API key")
    ten_model = _TEN_MODEL.get(settings.image_provider, "model sinh ảnh")

    if status == 429:
        # Ca đã gặp thật với Google: key hợp lệ, model văn bản gọi được, nhưng
        # mọi model sinh ảnh trả limit: 0 vì gói free không cấp hạn mức cho chúng.
        if "limit: 0" in than or "free_tier" in than:
            return "Tài khoản chưa được cấp hạn mức sinh ảnh. Cần bật thanh toán (billing) cho project rồi thử lại."
        return "Đang có quá nhiều yêu cầu sinh ảnh. Thử lại sau một phút nhé."
    if status in (401, 403):
        return f"{ten_key} không hợp lệ hoặc chưa được cấp quyền gọi model sinh ảnh."
    if status == 404:
        return f"Không tìm thấy model sinh ảnh. Kiểm tra lại {ten_model}."
    if status == 400:
        # Ark trả 400 kèm lý do khi nó không xử lý nổi ảnh gốc. Đó là lỗi phía
        # DỮ LIỆU, không phải lỗi cách người dùng mô tả — bảo họ "mô tả ngắn gọn
        # hơn" là chỉ sai chỗ, họ sửa mãi không hết.
        if "downloading" in than or "InvalidParameter" in than:
            return "Không xử lý được ảnh gốc của căn. Bạn thử chọn ảnh khác giúp mình nhé."
        return "Yêu cầu sửa ảnh không hợp lệ. Bạn thử mô tả ngắn gọn và cụ thể hơn nhé."
    return "Dịch vụ sinh ảnh đang gặp sự cố. Thử lại sau ít phút."


async def _goi_gemini(goc: bytes, mime: str, yeu_cau: str) -> httpx.Response:
    payload = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(goc).decode()}},
                    {"text": _HUONG_DAN.format(yeu_cau=yeu_cau)},
                ]
            }
        ]
    }
    url = _API_GEMINI.format(model=settings.gemini_image_model)
    async with httpx.AsyncClient(timeout=settings.image_timeout_s) as client:
        return await client.post(url, params={"key": settings.google_api_key}, json=payload)


async def _goi_seedream(goc: bytes, mime: str, yeu_cau: str) -> httpx.Response:
    """Gọi Seedream 4.0 qua BytePlus ModelArk.

    Endpoint tên là `images/generations` nhưng nhận CẢ ảnh gốc: có trường `image`
    thì nó sửa ảnh đó thay vì vẽ từ chữ (Ark gọi là I2I). Thiếu trường này thì
    tính năng đổi nghĩa hoàn toàn — từ "sửa nội thất của căn" thành "vẽ một căn
    hộ tưởng tượng" — mà không lỗi nào báo.

    Gửi ảnh bằng DATA URI chứ không phải link, dù Ark tải link được (đã thử với
    chính link Drive của dự án, 200 OK). Lý do: `_tai_anh()` phía trên đã tải
    bytes rồi để kiểm trần 8 MB và kiểm đúng là ảnh — truyền link là bỏ qua hai
    chốt đó và giao việc tải cho một máy chủ mình không kiểm soát.

    Nhận `b64_json` chứ không `url` vì hàm này phải trả bytes, và ảnh sinh ra
    KHÔNG được lưu ở đâu (xem docstring đầu file). Lấy URL thì phải tải vòng hai
    từ CDN ByteDance — thêm 1,3s, thêm một điểm hỏng, và link đó tự xoá sau 7
    ngày (header `expiry-date`), một cái bẫy cho người sửa code sau.
    """
    async with httpx.AsyncClient(timeout=settings.image_timeout_s) as client:
        return await client.post(
            _API_SEEDREAM,
            headers={"Authorization": f"Bearer {settings.ark_api_key}"},
            json={
                "model": settings.seedream_model,
                "prompt": _HUONG_DAN.format(yeu_cau=yeu_cau),
                "image": f"data:{mime};base64,{base64.b64encode(goc).decode()}",
                # Người dùng đang chờ MỘT ảnh thay cho ảnh họ vừa xem. Để "auto"
                # thì model tự quyết sinh cả loạt.
                "sequential_image_generation": "disabled",
                "response_format": "b64_json",
                "size": settings.seedream_size,
                "stream": False,
                "watermark": settings.seedream_watermark,
            },
        )


def _doc_anh_seedream(data: dict[str, Any]) -> tuple[bytes, str]:
    muc = (data.get("data") or [{}])[0]
    if not muc.get("b64_json"):
        raise ImageEditError("Dịch vụ không trả về ảnh nào. Bạn thử mô tả lại yêu cầu cụ thể hơn nhé.")
    # Đo thật: Seedream trả JPEG (đầu file FF D8 FF), không phải PNG như OpenAI.
    return base64.b64decode(muc["b64_json"]), "image/jpeg"


async def _goi_openai(goc: bytes, mime: str, yeu_cau: str) -> httpx.Response:
    """Gọi `/v1/images/edits` — endpoint SỬA ảnh có sẵn, không phải sinh từ chữ.

    Nhiều model ảnh chỉ sinh từ chữ; tính năng này bắt buộc phải nhận ảnh gốc.
    """
    async with httpx.AsyncClient(timeout=settings.image_timeout_s) as client:
        return await client.post(
            _API_OPENAI,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": settings.openai_image_model,
                "prompt": _HUONG_DAN.format(yeu_cau=yeu_cau),
                "n": "1",
                "size": settings.openai_image_size,
            },
            files={"image": ("anh-goc", goc, mime)},
        )


def _doc_anh_openai(data: dict[str, Any]) -> tuple[bytes, str]:
    muc = (data.get("data") or [{}])[0]
    if not muc.get("b64_json"):
        raise ImageEditError("Dịch vụ không trả về ảnh nào. Bạn thử mô tả lại yêu cầu cụ thể hơn nhé.")
    # Endpoint edits luôn trả PNG.
    return base64.b64decode(muc["b64_json"]), "image/png"


_MIME_CHO_PHEP = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp"})

_DATA_URI = re.compile(r"^data:(?P<mime>image/[a-zA-Z0-9.+-]{1,24});base64,(?P<du_lieu>[A-Za-z0-9+/=\s]+)$")


def _doc_anh_nguon(anh_nguon: str) -> tuple[bytes, str]:
    """Giải mã data URI client gửi lên, để sửa TIẾP trên ảnh AI vừa sinh.

    Ảnh AI cố ý không được lưu ở đâu (xem docstring đầu file), nên lượt sau
    server không có cách nào tự tìm lại nó — client phải gửi lại. Đường này
    KHÔNG đi tải gì cả nên không mở ra SSRF, nhưng byte thì do client kiểm soát,
    nên kiểm đủ ba thứ trước khi tiêu tiền gọi nhà cung cấp: đúng hình dạng data
    URI, MIME nằm trong danh sách cho phép, và không vượt trần kích thước.
    """
    khop = _DATA_URI.match(anh_nguon.strip())
    if khop is None:
        raise ImageEditError("Ảnh nguồn không đúng định dạng. Thử sửa lại từ ảnh gốc của căn nhé.")

    mime = khop.group("mime").lower()
    if mime not in _MIME_CHO_PHEP:
        raise ImageEditError("Ảnh nguồn dùng định dạng không hỗ trợ.")

    try:
        # `validate=True`: base64 mặc định BỎ QUA ký tự lạ, nên chuỗi rác vẫn
        # decode ra vài byte vô nghĩa rồi hỏng tận lúc gọi nhà cung cấp.
        goc = base64.b64decode(re.sub(r"\s", "", khop.group("du_lieu")), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ImageEditError("Ảnh nguồn không giải mã được. Thử sửa lại từ ảnh gốc của căn nhé.") from exc

    if not goc:
        raise ImageEditError("Ảnh nguồn rỗng.")
    if len(goc) > _TRAN_ANH_BYTE:
        raise ImageEditError("Ảnh nguồn quá lớn.")
    return goc, mime


async def sua_anh_can(
    ma_can: str,
    image_id: int,
    yeu_cau: str,
    anh_nguon: str | None = None,
) -> tuple[bytes, str]:
    """Sinh ảnh mới từ ảnh gốc của căn. Trả (bytes, mime).

    Không lưu ở đâu cả — người gọi tự quyết định đưa về client thế nào.

    `anh_nguon` có thì sửa tiếp trên đó thay vì ảnh gốc. `ma_can`/`image_id`
    VẪN bắt buộc và vẫn được tra: chúng buộc yêu cầu vào một căn có thật, kể cả
    khi byte ảnh đến từ client.
    """
    nha_cung_cap = settings.image_provider
    if not settings.image_edit_enabled:
        ten_key = _TEN_KEY.get(nha_cung_cap, "API key")
        raise ImageEditError(f"Tính năng sửa ảnh chưa được cấu hình. Điền {ten_key} trong .env ở gốc repo.")

    if anh_nguon:
        # Tra ảnh gốc DÙ không dùng tới byte của nó — đây là phép kiểm quyền:
        # cặp (ma_can, image_id) phải có thật, nếu không hàm dưới ném lỗi.
        _anh_cua_can(ma_can, image_id)
        goc, mime = _doc_anh_nguon(anh_nguon)
    else:
        goc, mime = await _tai_anh(_anh_cua_can(ma_can, image_id))

    try:
        goi = {"openai": _goi_openai, "seedream": _goi_seedream}.get(nha_cung_cap, _goi_gemini)
        response = await goi(goc, mime, yeu_cau)
    except httpx.HTTPError as exc:
        logger.exception("Không gọi được dịch vụ sinh ảnh (%s)", nha_cung_cap)
        raise ImageEditError("Không kết nối được dịch vụ sinh ảnh. Thử lại sau ít phút.") from exc

    if response.status_code >= 400:
        than = response.text[:600]
        # Không log `yeu_cau`: đó là chữ người dùng gõ.
        logger.error("%s trả %s: %s", nha_cung_cap, response.status_code, than)
        raise ImageEditError(_loi_tu_status(response.status_code, than))

    data = response.json()
    doc = {"openai": _doc_anh_openai, "seedream": _doc_anh_seedream}.get(nha_cung_cap, _doc_anh_tra_ve)
    return doc(data)
