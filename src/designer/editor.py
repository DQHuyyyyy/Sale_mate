"""Điều phối một lượt sửa ảnh: hỏi lại → khoanh vùng → gọi model → ghép.

Thứ tự các bước là có chủ ý về CHI PHÍ. Lượt gọi đắt (sinh ảnh) đứng SAU cùng,
sau khi một lượt gọi rẻ đã xác nhận yêu cầu đủ rõ và đã biết sửa chỗ nào. Yêu
cầu mơ hồ kiểu "làm đẹp hơn đi" dừng ở bước một và không tốn đồng nào.

Bảo đảm "chỉ đổi phần được nhắc tới" KHÔNG nằm ở đây và cũng không nằm ở model —
nó nằm ở `pipeline.ghep_de`. Xem chú thích đầu file đó.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from PIL import Image

from src.core.exceptions import UpstreamError
from src.core.logging import get_logger
from src.designer.pipeline import (
    Vung,
    chuan_hoa_kich_thuoc,
    doc_anh,
    doc_anh_tren_nen,
    dong_nhan,
    dung_mask,
    ghep_de,
    ty_le_be_phang,
    ty_le_doi,
    xuat_png,
)
from src.designer.prompts import khoi_sua_anh
from src.services.designer import BoDinhVi, ImageEditor

logger = get_logger(__name__)

NHAN = "Ảnh minh hoạ do AI tạo"

# Ba thao tác, mỗi cái một khối quy tắc trong prompts/sua_anh_*.md.
THEM = "them"
XOA = "xoa"
THAY_THE = "thay_the"
DOI_THUOC_TINH = "doi_thuoc_tinh"
THAO_TAC = frozenset({THEM, XOA, THAY_THE, DOI_THUOC_TINH})

# Model hay bọc JSON trong ```json ... ``` dù đã dặn đừng — cùng bệnh với PlanNode.
_KHOI_JSON = re.compile(r"\{.*\}", re.DOTALL)

CAU_HOI_MAC_DINH = "Bạn muốn mình sửa chi tiết nào trong ảnh? Nói rõ giúp mình vật thể và thay đổi mong muốn nhé."

# Dưới ngưỡng này coi như model không đổi gì. 0,5% diện tích là rất nhỏ — một
# vật thể cỡ cái quạt trong ảnh phòng khách đã chiếm nhiều hơn thế.
NGUONG_CO_DOI = 0.005
# Trên ngưỡng này coi như model bỏ cuộc và trả về mảng màu phẳng.
NGUONG_BE_PHANG = 0.02

KHONG_DOI_DUOC = (
    "Mình chưa thay đổi được gì trên ảnh này. Bạn thử nói cụ thể hơn xem — ví dụ tên đồ vật và thay đổi mong muốn."
)
HONG_ANH = (
    "Lần này mình chỉnh hỏng ảnh nên không đưa ra cho bạn. Bạn thử diễn đạt lại "
    "yêu cầu, hoặc chọn một chi tiết khác nhé."
)


@dataclass(frozen=True)
class KetQuaSua:
    """Kết quả một lượt: hoặc ảnh đã sửa, hoặc một câu hỏi ngược."""

    anh_png: bytes | None = None
    cau_hoi: str = ""
    doi_tuong: str = ""

    @property
    def can_hoi_them(self) -> bool:
        return self.anh_png is None


class ImageEditService:
    """Chạy một lượt sửa ảnh từ đầu đến cuối."""

    def __init__(
        self,
        bo_dinh_vi: BoDinhVi,
        editor: ImageEditor,
        *,
        canh_toi_da: int = 1536,
        dung_mask: bool = False,
    ) -> None:
        self._bo_dinh_vi = bo_dinh_vi
        self._editor = editor
        self._canh_toi_da = canh_toi_da
        self._dung_mask = dung_mask

    async def sua(self, *, anh_goc: bytes, lenh: str) -> KetQuaSua:
        goc = doc_anh(anh_goc)

        ke_hoach = self._doc_ke_hoach(await self._bo_dinh_vi.dinh_vi(anh=anh_goc, lenh=lenh))
        if ke_hoach is None or not ke_hoach.get("ro_rang"):
            cau_hoi = (ke_hoach or {}).get("cau_hoi") or CAU_HOI_MAC_DINH
            logger.info("Yêu cầu chưa đủ rõ, hỏi lại thay vì sinh ảnh")
            return KetQuaSua(cau_hoi=str(cau_hoi).strip())

        # Khung toạ độ CHỈ cần khi bật mask. Tắt mask thì bỏ qua hẳn, và nhờ vậy
        # cả tính năng thoát khỏi phụ thuộc vào thứ chỉ đúng ~21,7% số lần.
        vung_goc = self._doc_khung(ke_hoach.get("khung"), goc.size)
        if self._dung_mask and vung_goc is None:
            logger.warning("Model trả khung toạ độ không dùng được")
            return KetQuaSua(cau_hoi=CAU_HOI_MAC_DINH)

        # Gửi model ở kích thước đã chuẩn hoá, rồi đưa về đúng khung ảnh gốc.
        kt = chuan_hoa_kich_thuoc(*goc.size, canh_toi_da=self._canh_toi_da)
        anh_gui = xuat_png(goc.resize(kt))
        mask = dung_mask(kt, vung_goc.theo_ty_le(goc.size, kt)) if self._dung_mask and vung_goc else None

        doi_tuong = str(ke_hoach.get("doi_tuong") or "").strip()
        # Nhãn lạ thì rơi về `doi_thuoc_tinh` — nó ít phá ảnh nhất trong ba loại.
        thao_tac = str(ke_hoach.get("thao_tac") or "").strip()
        if thao_tac not in THAO_TAC:
            logger.info("Thao tác %r không nhận ra, dùng %s", thao_tac, DOI_THUOC_TINH)
            thao_tac = DOI_THUOC_TINH

        moi = await self._editor.edit(
            anh=anh_gui,
            mask=mask,
            lenh=self._lenh_cho_model(lenh, doi_tuong, thao_tac),
            kich_thuoc=f"{kt[0]}x{kt[1]}",
        )

        # Trong suốt = model không làm được chỗ đó. Lấy lại pixel gốc, KHÔNG tô
        # đen — đây chính là lỗi khối đen giữa phòng khách đã gặp.
        ket_qua = self._hoan_thien(goc, doc_anh_tren_nen(moi, goc), vung_goc)

        loi = self._kiem_ket_qua(goc, ket_qua)
        if loi:
            return KetQuaSua(cau_hoi=loi)

        return KetQuaSua(anh_png=xuat_png(dong_nhan(ket_qua, NHAN)), doi_tuong=doi_tuong)

    @staticmethod
    def _kiem_ket_qua(goc: Image.Image, ket_qua: Image.Image) -> str:
        """Trả thông điệp lỗi nếu ảnh ra không dùng được, chuỗi rỗng nếu ổn.

        Không có bước này thì trợ lý báo "Mình đã chỉnh quạt theo yêu cầu" kể cả
        khi ảnh y nguyên hoặc có một khối đen giữa phòng — đúng chuyện đã xảy
        ra. Khẳng định sai như vậy vi phạm thẳng nguyên tắc số 1 của dự án.
        """
        be_phang = ty_le_be_phang(goc, ket_qua)
        if be_phang > NGUONG_BE_PHANG:
            logger.warning("Ảnh ra có %.1f%% mảng màu phẳng, coi như hỏng", be_phang * 100)
            return HONG_ANH

        doi = ty_le_doi(goc, ket_qua)
        if doi < NGUONG_CO_DOI:
            logger.info("Ảnh ra chỉ khác %.2f%%, coi như không đổi gì", doi * 100)
            return KHONG_DOI_DUOC

        return ""

    def _hoan_thien(self, goc: Image.Image, moi: Image.Image, vung: Vung | None) -> Image.Image:
        """Đưa ảnh model trả về đúng khung hình ảnh gốc.

        Bật mask thì ghép: chỉ lấy phần trong khung, phần ngoài giữ pixel gốc.

        Tắt mask thì lấy TOÀN BỘ ảnh model, chỉ resize về đúng kích thước gốc.
        Đây chính là điều khiến kết quả bằng được ChatGPT: model tự tìm vật thể
        rồi vẽ lại cả khung, không bị ta chặn bằng một khung toạ độ đoán sai.

        Cái mất là bảo đảm "không đổi thứ không được nhắc tới" — nay chỉ còn
        `input_fidelity` và prompt giữ giúp, không còn gì cưỡng chế.
        """
        if self._dung_mask and vung is not None:
            return ghep_de(goc, moi, vung)
        return moi if moi.size == goc.size else moi.resize(goc.size, Image.LANCZOS)

    @staticmethod
    def _lenh_cho_model(lenh: str, doi_tuong: str, thao_tac: str) -> str:
        """Ghép quy tắc chung với đúng khối quy tắc của thao tác đang làm.

        Ba thao tác cần dặn khác hẳn nhau: xoá thì PHẢI vẽ thêm nền, còn đổi
        thuộc tính thì TUYỆT ĐỐI không được vẽ thêm gì. Bản trước gộp làm một và
        dặn "không thêm vật thể mới" cho mọi trường hợp — chính câu đó đẩy model
        vào thế bí khi phải xoá cái quạt, và nó trả về một vùng trống.

        Nội dung quy tắc nằm ở `prompts/sua_anh_*.md`, không hardcode ở đây, để
        chỉnh prompt là một diff đọc được và so được với bản trước.
        """
        khoi = khoi_sua_anh()
        rieng = khoi.get(thao_tac) or khoi.get(DOI_THUOC_TINH, "")
        nhac = f"Chỉ thay đổi: {doi_tuong}.\n" if doi_tuong else ""

        return f"{nhac}Yêu cầu: {lenh.strip()}\n\n{khoi.get('chung', '')}\n\n{rieng}".strip()

    @staticmethod
    def _doc_ke_hoach(raw: str) -> dict[str, Any] | None:
        khop = _KHOI_JSON.search(raw or "")
        if khop is None:
            return None
        try:
            ke_hoach = json.loads(khop.group())
        except json.JSONDecodeError:
            return None
        return ke_hoach if isinstance(ke_hoach, dict) else None

    @staticmethod
    def _doc_khung(khung: Any, kich_thuoc: tuple[int, int]) -> Vung | None:
        """Đổi khung tương đối 0..1 của model sang pixel, có kiểm tra.

        Model trả toạ độ ngoài khoảng, đảo đầu đuôi, hoặc thiếu phần tử đều là
        chuyện xảy ra thật. Khung hỏng mà không bắt ở đây thì mask sai chỗ, và
        ảnh ra vẫn "trông hợp lý" nên rất khó lần ra.
        """
        if not isinstance(khung, (list, tuple)) or len(khung) != 4:
            return None
        try:
            x0, y0, x1, y1 = (float(v) for v in khung)
        except (TypeError, ValueError):
            return None

        rong, cao = kich_thuoc
        vung = Vung(
            trai=int(min(max(min(x0, x1), 0.0), 1.0) * rong),
            tren=int(min(max(min(y0, y1), 0.0), 1.0) * cao),
            phai=int(min(max(max(x0, x1), 0.0), 1.0) * rong),
            duoi=int(min(max(max(y0, y1), 0.0), 1.0) * cao),
        )
        return vung if vung.hop_le else None


async def tai_anh(url: str, *, timeout_s: float = 30.0, toi_da_bytes: int = 12 * 1024 * 1024) -> bytes:
    """Tải ảnh gốc từ URL công khai của portal.

    Chặn theo kích thước vì URL đến từ client: không có trần thì một link tới
    file vài trăm MB đủ làm nghẽn tiến trình lõi AI.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Không tải được ảnh gốc: %s", exc)
        raise UpstreamError("Không tải được ảnh của căn này. Thử lại sau ít phút.") from exc

    if len(response.content) > toi_da_bytes:
        raise UpstreamError("Ảnh gốc quá lớn để xử lý.")
    return response.content
