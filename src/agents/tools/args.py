"""Đọc tham số tool do model sinh ra, chịu được giá trị ngoài đặc tả.

Vì sao cần: model điền `sort="price"` trong khi schema chỉ nhận
`gia_tang | gia_giam | dien_tich_tang | dien_tich_giam`. Pydantic từ chối, tool
trả `failure`, và agent mất SẠCH dữ liệu — trong khi mọi tham số còn lại
(`price_max`, `unit_type`…) đều hợp lệ và đủ để trả lời.

Nguyên tắc của dự án là "không bịa", và nó được thực thi bằng KIẾN TRÚC chứ
không bằng cách tin model. Model là thành phần xác suất, sẽ có lần trả ra thứ
ngoài đặc tả. Việc của tầng này là làm hậu quả trở nên vô hại: bỏ đúng trường
sai, giữ lại phần dùng được.

Đi kèm `_mo_ta_tham_so` trong `nodes/plan.py`: chỗ đó nói cho model biết giá trị
nào hợp lệ, chỗ này chặn hậu quả khi nó vẫn đoán. Thiếu vế thứ hai là lại đang
tin model.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from src.core.logging import get_logger

logger = get_logger(__name__)

M = TypeVar("M", bound=BaseModel)


def doc_tham_so(
    schema: type[M],
    tho: dict[str, Any],
    *,
    co_the_bo: set[str] | None = None,
) -> tuple[M, list[str]]:
    """Dựng args, bỏ qua những trường model điền sai — nhưng CHỈ trong `co_the_bo`.

    Trả về (tham số đã dựng, tên các trường bị bỏ).

    `co_the_bo` phải liệt kê tường minh, mặc định rỗng nghĩa là nghiêm ngặt như
    cũ. Chỉ nên cho vào đây trường KHÔNG đổi tập kết quả — `sort`, `limit` — tức
    trường trình bày.

    Vì sao không bỏ bừa: `inventory_lookup(unit_code=123)` sai kiểu, bỏ
    `unit_code` đi thì tool hết bộ lọc và trả về TOÀN BỘ tồn kho. Người dùng hỏi
    một căn, nhận cả kho, mà không có dấu hiệu gì là đã sai. Với trường lọc thì
    hỏng to tiếng vẫn tốt hơn tự ý nới rộng câu hỏi.

    Trường BẮT BUỘC sai hoặc thiếu cũng luôn raise: thiếu `von_tu_co` là không
    tính được khoản vay, im lặng bỏ qua rồi trả kết quả sai còn tệ hơn báo lỗi.
    """
    duoc_bo = co_the_bo or set()
    # Trường model bịa hẳn tên thì pydantic mặc định IM LẶNG bỏ qua. Tool không
    # chết, nhưng model tưởng đã lọc theo tiêu chí đó và có thể khẳng định vậy
    # với khách. Bắt riêng để còn báo ngược lại cho nó.
    la = sorted(set(tho) - set(schema.model_fields))
    con_lai = {k: v for k, v in tho.items() if k not in la}
    bo_qua: list[str] = list(la)
    if la:
        logger.info("Bỏ tham số không có trong schema: %s", ", ".join(la))

    # Mỗi vòng bỏ ít nhất một trường, nên không thể lặp quá số trường ban đầu.
    for _ in range(len(tho) + 1):
        try:
            return schema(**con_lai), bo_qua
        except ValidationError as exc:
            hong = {str(e["loc"][0]) for e in exc.errors() if e.get("loc")}
            # Chỉ bỏ trường ĐANG CÓ và được phép bỏ. Lỗi "thiếu trường bắt buộc"
            # không nằm trong `con_lai`, còn trường lọc không nằm trong `duoc_bo`
            # — cả hai đều cho tập giao rỗng và lỗi nổi lên, đúng ý muốn.
            hong &= set(con_lai) & duoc_bo
            if not hong:
                raise
            for ten in sorted(hong):
                con_lai.pop(ten, None)
                bo_qua.append(ten)
            logger.info("Bỏ tham số ngoài đặc tả: %s", ", ".join(sorted(hong)))

    return schema(**con_lai), bo_qua
