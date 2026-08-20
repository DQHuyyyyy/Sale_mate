"""Bộ đếm chi phí theo ngày, dùng để phanh nhánh leo thang.

Vì sao cần: ngân sách Anthropic của dự án là $5, tức khoảng trăm lượt orchestrator.
Không có phanh thì một buổi debug đốt sạch, và lần sau khách hỏi thì nhánh leo
thang im lặng hỏng vì hết credit — hỏng câm, không ai biết cho tới lúc xem log.

Đếm trong BỘ NHỚ TIẾN TRÌNH, cố ý không dùng Redis hay bảng riêng:

- Quy mô hiện tại là một tiến trình lõi AI. Thêm một phụ thuộc hạ tầng để đếm
  vài trăm con số một ngày là đổi lấy nhiều rủi ro hơn mức nó chặn được.
- Khởi động lại là mất số đếm, tức hạn mức được nới ngoài ý muốn. Chấp nhận
  được: đây là phanh chống tai nạn, không phải hạn mức tính tiền. Bảng giá
  chính thức vẫn nằm ở nhà cung cấp.

Chạy nhiều tiến trình thì mỗi tiến trình có hạn mức riêng — đặt ngưỡng bằng
tổng chia số tiến trình, hoặc chuyển sang bộ đếm dùng chung.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.gia_model import chi_phi_usd
from src.core.logging import get_logger

logger = get_logger(__name__)


class SoChiTieu:
    """Cộng dồn chi phí trong NGÀY, tự đặt lại khi sang ngày mới."""

    def __init__(self) -> None:
        self._ngay = self._hom_nay()
        self._da_tieu = 0.0
        self._so_luot = 0

    @staticmethod
    def _hom_nay() -> str:
        # UTC chứ không phải giờ máy: server và máy dev khác múi giờ thì cùng
        # một mốc "sang ngày mới" mới so sánh được log của hai bên.
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _xoay_ngay(self) -> None:
        hom_nay = self._hom_nay()
        if hom_nay != self._ngay:
            logger.info("Sang ngày mới, đặt lại bộ đếm chi phí (hôm qua $%.4f)", self._da_tieu)
            self._ngay, self._da_tieu, self._so_luot = hom_nay, 0.0, 0

    def ghi_nhan(
        self,
        model: str,
        *,
        token_vao: int,
        token_ra: int,
        token_cache: int = 0,
        token_ghi_cache: int = 0,
    ) -> float:
        """Cộng chi phí một lượt, trả về tổng đã tiêu trong ngày."""
        self._xoay_ngay()
        tien = chi_phi_usd(
            model,
            token_vao=token_vao,
            token_ra=token_ra,
            token_doc_cache=token_cache,
            token_ghi_cache=token_ghi_cache,
        )
        if tien is not None:
            self._da_tieu += tien
            self._so_luot += 1
            logger.info("Leo thang tốn $%.4f, tổng hôm nay $%.4f", tien, self._da_tieu)
        return self._da_tieu

    def con_ngan_sach(self, tran_usd: float) -> bool:
        """Còn được tiêu nữa không. `tran_usd <= 0` nghĩa là KHÔNG giới hạn.

        Ngưỡng 0 phải là "không giới hạn" chứ không phải "cấm hẳn": biến môi
        trường thiếu sẽ về 0, và mặc định không được là tắt âm thầm một tính
        năng người ta vừa bật.
        """
        if tran_usd <= 0:
            return True
        self._xoay_ngay()
        con = self._da_tieu < tran_usd
        if not con:
            logger.warning(
                "Chạm trần ngân sách ngày $%.2f sau %s lượt — nhánh leo thang tạm tắt",
                tran_usd,
                self._so_luot,
            )
        return con

    def tom_tat(self) -> dict[str, object]:
        self._xoay_ngay()
        return {"ngay": self._ngay, "da_tieu_usd": round(self._da_tieu, 4), "so_luot": self._so_luot}

    def dat_lai(self) -> None:
        """Chỉ dùng trong test — mỗi test phải bắt đầu từ số 0."""
        self._ngay, self._da_tieu, self._so_luot = self._hom_nay(), 0.0, 0


# Một bộ đếm cho cả tiến trình. Cùng kiểu với `vocabulary` trong tools/search.py.
so_chi_tieu = SoChiTieu()
