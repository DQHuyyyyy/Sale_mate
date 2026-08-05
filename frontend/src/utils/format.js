// Hiển thị số/ngày theo lối Việt. Ưu tiên chuỗi text backend trả về, chỉ tự
// dựng khi cột text trống.

export function formatPrice(giaText, giaTri) {
  if (giaText) return giaText;
  if (giaTri === null || giaTri === undefined || giaTri === '') return '—';
  return `${Number(giaTri).toLocaleString('vi-VN', { maximumFractionDigits: 3 })} tỷ`;
}

export function formatArea(dienTichText, dienTichSo) {
  if (dienTichText) return dienTichText;
  if (dienTichSo === null || dienTichSo === undefined || dienTichSo === '') return '—';
  return `${Number(dienTichSo).toLocaleString('vi-VN')} m²`;
}

export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function orDash(value) {
  return value === null || value === undefined || value === '' ? '—' : value;
}

/**
 * Gộp các cách viết trùng nghĩa của loại căn.
 * Dữ liệu thật có cả '1 PN, 1WC', '1PN, 1 WC' và '1PN, 1WC' cho cùng một loại —
 * dropdown chỉ nên hiện một mục. Giữ lại cách viết xuất hiện đầu tiên; backend
 * cũng bỏ khoảng trắng khi so khớp nên chọn biến thể nào cũng ra đủ căn.
 */
export function uniqueTypes(apartments) {
  const seen = new Map();
  apartments.forEach((item) => {
    const label = item.loai_can;
    if (!label) return;
    const key = label.replace(/\s+/g, '').toLowerCase();
    if (!seen.has(key)) seen.set(key, label);
  });
  return [...seen.values()].sort((a, b) => a.localeCompare(b, 'vi'));
}
