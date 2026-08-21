"""Tham số định lượng của chính sách hỗ trợ lãi suất.

Vì sao tách khỏi Qdrant: văn bản chính sách là văn xuôi, hợp cho truy hồi và
trích dẫn, nhưng rút số ra từ văn xuôi bằng model là chỗ sinh lỗi. Con số nào
dùng để TÍNH thì phải nằm ở dạng có cấu trúc — cùng lý lẽ đã áp cho giá và tình
trạng căn (xem `tools/inventory.py`).

Vì sao là file JSON trong repo chứ không phải bảng Postgres: chính sách đổi vài
lần một năm, và migration trên dự án này chạy thẳng lên production (Supabase
dùng chung). Để trong repo thì mỗi lần đổi là một PR có người review. Cần
chuyển sang DB về sau thì chỉ thay thân `tai_chinh_sach()`, mặt ngoài giữ nguyên.

Điều quan trọng nhất ở đây là `hieu_luc_den`. Chính sách bất động sản có hạn:
bản 6%/5 năm chỉ áp dụng cho khách mua 20/4–20/7/2026, và nó đã thay bản 9%
công bố trước đó một tháng. Không đọc ngày thì tool sẽ báo một ưu đãi đã hết
cho khách đang hỏi hôm nay.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

FILE_THAM_SO = Path(__file__).resolve().parent / "data" / "chinh_sach_vay.json"


class GoiHoTro(BaseModel):
    """Một gói hỗ trợ — khách chọn thời gian dài hơn thì trả thêm vào GIÁ.

    `phu_phi` là phần trăm cộng vào giá cơ sở, KHÔNG phải lãi suất. Nhầm hai
    thứ này là sai số hàng trăm triệu.
    """

    so_thang: int
    mien_lai: bool = False
    phu_phi: dict[str, float] = Field(default_factory=dict)

    def phu_phi_theo_muc_vay(self, muc_vay: int) -> float | None:
        """Phụ phí ở mức vay 70% hay 80%. Mức lạ thì trả None, không nội suy."""
        return self.phu_phi.get(str(muc_vay))


class ChinhSachVay(BaseModel):
    """Một chính sách hỗ trợ lãi suất, kèm khoảng thời gian hiệu lực."""

    ma: str
    ten: str
    doc_id: str = ""
    nguon: str = ""
    hieu_luc_tu: date
    hieu_luc_den: date
    tran_lai_suat: float
    so_thang_khoa: int
    tran_sau_uu_dai: float | None = None
    so_thang_tiep_suc: int = 0
    goi_duoc_tiep_suc_toi_da_thang: int = 0
    ky_han_vay_nam_min: int = 20
    ky_han_vay_nam_max: int = 35
    muc_vay_ho_tro: list[int] = Field(default_factory=list)
    goi: list[GoiHoTro] = Field(default_factory=list)

    def con_hieu_luc(self, ngay: date) -> bool:
        return self.hieu_luc_tu <= ngay <= self.hieu_luc_den

    def muc_vay_phu_hop(self, ty_le_vay: float) -> int | None:
        """Mức hỗ trợ nhỏ nhất phủ được tỷ lệ vay này.

        Vay 55% thì rơi vào mức 70% — gói ở mức thấp hơn luôn có phụ phí nhẹ
        hơn nên chọn mức nhỏ nhất phủ đủ là có lợi cho khách. Vượt mức cao nhất
        thì trả None: không được nội suy ra một con số chính sách không nói.
        """
        for muc in sorted(self.muc_vay_ho_tro):
            if ty_le_vay <= muc:
                return muc
        return None


@lru_cache(maxsize=1)
def tai_chinh_sach() -> list[ChinhSachVay]:
    """Đọc bảng tham số. Cache vì file chỉ đổi khi deploy bản mới."""
    raw = json.loads(FILE_THAM_SO.read_text(encoding="utf-8"))
    return [ChinhSachVay(**muc) for muc in raw.get("chinh_sach", [])]


def chinh_sach_dang_ap_dung(ngay: date | None = None) -> ChinhSachVay | None:
    """Chính sách còn hiệu lực vào `ngay`, hoặc None nếu không có cái nào.

    Trả None là một câu trả lời HỢP LỆ, không phải lỗi: giữa hai đợt chính sách
    thì đúng là không có ưu đãi nào áp dụng. Chỗ gọi phải nói thẳng điều đó
    thay vì rơi về chính sách gần nhất.
    """
    hom_nay = ngay or date.today()
    con_hieu_luc = [cs for cs in tai_chinh_sach() if cs.con_hieu_luc(hom_nay)]
    # Nhiều chính sách chồng ngày thì lấy cái mới công bố nhất.
    return max(con_hieu_luc, key=lambda cs: cs.hieu_luc_tu, default=None)


def chinh_sach_gan_nhat_da_het(ngay: date | None = None) -> ChinhSachVay | None:
    """Chính sách vừa hết hạn gần đây nhất — để nói rõ "hết ngày nào".

    Nói "chưa có chính sách nào" thì khách tưởng chưa bao giờ có. Nói "bản gần
    nhất hết hiệu lực 20/7/2026" mới đủ để họ biết nên hỏi lại chủ đầu tư.
    """
    hom_nay = ngay or date.today()
    da_het = [cs for cs in tai_chinh_sach() if cs.hieu_luc_den < hom_nay]
    return max(da_het, key=lambda cs: cs.hieu_luc_den, default=None)
