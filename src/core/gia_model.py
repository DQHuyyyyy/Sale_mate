"""Bảng giá model và quy đổi token → USD.

Vì sao cần một chỗ riêng: ngân sách API của dự án là $5 mỗi nhà cung cấp, tức
mọi quyết định "đổi model nào" đều là quyết định tiền bạc. Không có bảng giá
trong code thì con số chi phí phải tính tay ngoài repo, và sẽ lệch ngay lần đầu
ai đó đổi `LLM_MODEL_ANSWER`.

Dùng ở hai chỗ: `src/eval/answer.py` báo chi phí mỗi lượt đo, và (về sau) bộ
đếm ngân sách ngày chặn vòng lặp orchestrator khi tiêu quá tay.

⚠️ Giá thay đổi theo thời gian và theo chương trình khuyến mại. Mỗi mục có cờ
`da_xac_minh` nói rõ con số lấy từ bảng giá thật hay từ trí nhớ — mục chưa xác
minh vẫn tính được nhưng ghi log WARNING, để không ai lỡ báo cáo một con số
tự tin mà sai.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GiaModel:
    """Giá USD trên MỘT TRIỆU token."""

    vao: float
    ra: float
    vao_cache: float | None = None
    da_xac_minh: bool = False
    ghi_chu: str = ""


# Giá đọc từ bảng giá công bố ngày 18/08/2026.
#
# Claude Sonnet 5 đang ở GIÁ GIỚI THIỆU $2/$10, hết hạn 31/08/2026, sau đó về
# $3/$15 — tức chi phí phần orchestrator tăng ~50%. Ai đọc file này sau mốc đó
# phải cập nhật, nếu không mọi ước tính ngân sách đều thấp hơn thực tế.
BANG_GIA: dict[str, GiaModel] = {
    # --- OpenAI, xác minh từ trang giá ---
    "gpt-5.6-luna": GiaModel(0.20, 1.20, 0.02, da_xac_minh=True),
    "gpt-5.6-terra": GiaModel(2.00, 12.00, 0.20, da_xac_minh=True),
    "gpt-5.6-sol": GiaModel(5.00, 30.00, 0.50, da_xac_minh=True),
    # --- Anthropic, xác minh từ trang giá ---
    "claude-sonnet-5": GiaModel(
        2.00,
        10.00,
        0.20,
        da_xac_minh=True,
        ghi_chu="giá giới thiệu, hết 31/08/2026 rồi về 3.00/15.00",
    ),
    # --- CHƯA XÁC MINH: lấy từ trí nhớ, cần đối chiếu trang giá trước khi
    # đem con số đi báo cáo. Giữ lại vì baseline hiện tại đang chạy gpt-4o.
    "gpt-4o": GiaModel(2.50, 10.00, 1.25),
    "gpt-4o-mini": GiaModel(0.15, 0.60, 0.075),
    "claude-opus-5": GiaModel(5.00, 25.00, 0.50),
    "text-embedding-3-small": GiaModel(0.02, 0.0),
}

_MOT_TRIEU = 1_000_000
# Anthropic tính ghi cache 1,25× giá vào (TTL 5 phút).
_HE_SO_GHI_CACHE = 1.25


def gia_cua(model: str) -> GiaModel | None:
    """Tra giá theo tên model. Trả None nếu chưa có trong bảng."""
    gia = BANG_GIA.get(model)
    if gia is None:
        logger.warning("Chưa có giá cho model %s — chi phí sẽ không được tính", model)
        return None
    if not gia.da_xac_minh:
        logger.warning("Giá của %s CHƯA XÁC MINH — đối chiếu trang giá trước khi báo cáo", model)
    return gia


def chi_phi_usd(
    model: str,
    *,
    token_vao: int = 0,
    token_ra: int = 0,
    token_doc_cache: int = 0,
    token_ghi_cache: int = 0,
) -> float | None:
    """Quy token ra USD. Trả None khi chưa biết giá model — KHÔNG đoán bằng 0.

    Trả 0.0 và trả None là hai chuyện khác nhau: 0.0 nghĩa là thật sự không tốn
    gì, None nghĩa là không biết. Gộp hai cái làm một thì một model thiếu giá sẽ
    im lặng kéo tổng chi phí xuống và bộ đếm ngân sách mất tác dụng.
    """
    gia = gia_cua(model)
    if gia is None:
        return None

    gia_cache = gia.vao_cache if gia.vao_cache is not None else gia.vao
    tong = (
        token_vao * gia.vao
        + token_ra * gia.ra
        + token_doc_cache * gia_cache
        # Ghi cache đắt hơn giá vào 25% — trả thêm một lần để những lượt
        # sau đọc lại với giá 0,1×. Bỏ qua nó là báo thiếu chi phí.
        + token_ghi_cache * gia.vao * _HE_SO_GHI_CACHE
    )
    return tong / _MOT_TRIEU
