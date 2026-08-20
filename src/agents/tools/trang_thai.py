"""Trạng thái một căn hộ — bảng nhãn dùng chung cho MỌI tool tồn kho.

Vì sao một file riêng: trước đây `inventory.py` và `so_sanh.py` mỗi bên giữ một
bản `_STATUS_LABEL` chép tay. Thêm một trạng thái mà chỉ sửa một bên thì cùng
một căn hiện hai nhãn khác nhau tuỳ vào việc khách hỏi "VOP397 còn không" hay
"so sánh VOP397 với VOP345" — và không có gì báo lỗi.

## Ba trạng thái, suy ra trong VIEW `inventory_units`

| `status`    | Nhãn         | Nghĩa                                   |
|-------------|--------------|-----------------------------------------|
| `available` | Còn          | chưa ai để lại thông tin                |
| `reserved`  | Đã đặt cọc   | có lead còn hiệu lực trong dat_coc_lead |
| `sold`      | Đã bán       | giao dịch xong                          |

Bản đầu có bốn, tách "Đang giữ chỗ" (lead mới) khỏi "Đã đặt cọc" (sale đã xác
nhận). Bỏ đi vì với người mua thì hai mức đó **không khác gì nhau** — cả hai đều
là "căn này có người rồi". Mức độ chín của lead là việc nội bộ của đội sale, đọc
ở cột `trang_thai` của bảng lead, không cần thành một trạng thái căn.

Xem [migration 010](../../../interface/backend/migrations/010_trang_thai_dat_coc.sql)
để biết trạng thái được suy ra từ `dat_coc_lead` thế nào.
"""

from __future__ import annotations

CON = "available"
DA_DAT_COC = "reserved"
DA_BAN = "sold"

NHAN: dict[str, str] = {
    CON: "Còn",
    DA_DAT_COC: "Đã đặt cọc",
    DA_BAN: "Đã bán",
}

# Trạng thái mà một khách MỚI vẫn mua được. Chỉ có một, và cố ý khai theo kiểu
# danh sách trắng: thêm trạng thái mới sau này thì mặc định là KHÔNG chào bán,
# an toàn hơn là mặc định chào rồi phát hiện sau.
CON_BAN_DUOC = frozenset({CON})

# Đang có người giữ nhưng CHƯA bán — vẫn hiện cho khách xem, kèm nhãn rõ. Cọc
# có thể huỷ, và giấu căn đi thì khách đang xem dở quay lại thấy nó biến mất mà
# không có lời giải thích nào.
DANG_CO_NGUOI_GIU = frozenset({DA_DAT_COC})


def nhan(status: str | None) -> str:
    """Nhãn tiếng Việt của một trạng thái. Giá trị lạ thì trả nguyên văn.

    Trả nguyên văn chứ không trả "Không rõ": nếu dữ liệu sinh ra một trạng thái
    ngoài bảng này thì phải nhìn thấy nó để đi sửa, không phải nuốt mất.
    """
    return NHAN.get(str(status or ""), str(status or ""))


def con_ban_duoc(status: str | None) -> bool:
    """Khách mới còn mua được căn này không."""
    return str(status or "") in CON_BAN_DUOC
