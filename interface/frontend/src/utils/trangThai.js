/**
 * Ba trạng thái căn — bảng nhãn dùng chung cho toàn bộ giao diện.
 *
 * Khớp `src/agents/tools/trang_thai.py` phía lõi AI. Hai bên phải nói giống
 * nhau: khách đọc "Đã đặt cọc" trong widget chat rồi bấm sang trang căn mà
 * thấy "Còn" thì không biết tin bên nào.
 *
 * Giá trị đến từ `tinh_trang_chi_tiet`, suy ra trong VIEW `inventory_units`
 * (migration 010). Chưa chạy migration đó thì trường này là null — rơi về
 * `tinh_trang` thô (Còn/Hết) để giao diện không trống.
 */

export const TRANG_THAI = {
  available: { nhan: 'Còn', lop: 'con' },
  reserved: { nhan: 'Đã đặt cọc', lop: 'dat-coc' },
  sold: { nhan: 'Đã bán', lop: 'da-ban' },
};

/** Nhãn tiếng Việt để hiện ra. Rơi về tình trạng thô khi chưa có bản chi tiết. */
export function nhanTrangThai(chiTiet, tho) {
  return TRANG_THAI[chiTiet]?.nhan ?? tho ?? '—';
}

/**
 * Hậu tố class cho chip trạng thái.
 *
 * Trả về lớp riêng cho từng mức chứ không chỉ "còn / không còn": giữ chỗ và
 * đặt cọc có thể huỷ, đã bán thì không — người dùng cần phân biệt được bằng
 * mắt, không phải đọc chữ mới biết.
 */
export function lopTrangThai(chiTiet, tho) {
  if (TRANG_THAI[chiTiet]) return TRANG_THAI[chiTiet].lop;
  return tho === 'Còn' ? 'con' : 'da-ban';
}

/** Khách mới còn mua được căn này không. */
export function conBanDuoc(chiTiet, tho) {
  if (chiTiet) return chiTiet === 'available';
  return tho === 'Còn';
}
