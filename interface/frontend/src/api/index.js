// Toàn bộ hàm gọi API, gom một chỗ để component chỉ cần import từ 'src/api'.
import { request, setToken } from './client';

export { ApiError, getToken, setToken, setUnauthorizedHandler } from './client';

// ---- Auth ----
export async function login(username, password) {
  const data = await request('/api/auth/login', {
    method: 'POST',
    body: { username, password },
  });
  setToken(data.token);
  return data.user;
}

export function getMe() {
  return request('/api/auth/me');
}

export function logout() {
  setToken(null);
}

// ---- Căn hộ ----
export function searchApartments({
  tower,
  priceMin,
  priceMax,
  priceMaxExclusive,
  subdivision,
  type,
  wc,
} = {}) {
  return request('/api/apartments', {
    params: {
      tower,
      price_min: priceMin,
      price_max: priceMax,
      // Trợ lý S bật cờ này cho câu "dưới 3 tỷ" — loại luôn căn giá đúng 3 tỷ,
      // để lưới bên trái đếm ra cùng con số với câu trả lời trong chat.
      price_max_exclusive: priceMaxExclusive || undefined,
      subdivision,
      type,
      // Tách khỏi `type` vì `type` khớp theo tiền tố: "căn 2 vệ sinh" không nêu
      // phòng ngủ nên không diễn đạt được bằng nó.
      wc,
    },
  });
}

export function getApartment(maCan) {
  return request(`/api/apartments/${encodeURIComponent(maCan)}`);
}

export function addApartment(payload) {
  return request('/api/apartments', { method: 'POST', body: payload });
}

export function uploadApartmentImages(maCan, files) {
  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append('files', file));
  return request(`/api/apartments/${encodeURIComponent(maCan)}/images`, {
    method: 'POST',
    formData,
  });
}

/**
 * Đặt một ảnh làm ảnh đại diện (admin).
 *
 * Ảnh đại diện là dòng có `sort_order` nhỏ nhất — chính thứ mà thẻ ở trang tìm
 * kiếm và ảnh đầu trong gallery cùng đọc, nên đổi một lần là cả hai đổi theo.
 */
export function datAnhDaiDien(maCan, imageId) {
  return request(`/api/apartments/${encodeURIComponent(maCan)}/images/${imageId}/dai-dien`, {
    method: 'PATCH',
  });
}

/** Xoá một ảnh khỏi căn (admin). Trả về căn đã cập nhật. */
export function xoaAnhCanHo(maCan, imageId) {
  return request(`/api/apartments/${encodeURIComponent(maCan)}/images/${imageId}`, {
    method: 'DELETE',
  });
}

// ---- Phân khu ----
export function getZones() {
  return request('/api/zones');
}

export function getTowers() {
  return request('/api/towers');
}

// ---- Lịch sử bán ----
export function getMySales() {
  return request('/api/sales/my-history');
}

export function getAllSales() {
  return request('/api/sales/all');
}


// ---- Quản lý sale ----
export function getSales() {
  return request('/api/users', { params: { role: 'sale' } });
}

/** Tạo tài khoản sale (admin). Vai trò do backend cố định là 'sale'. */
export function createSaleAccount({ username, password, fullName, phone, email }) {
  return request('/api/users', {
    method: 'POST',
    body: {
      username: username.trim(),
      password,
      full_name: fullName.trim(),
      phone: phone?.trim() || null,
      email: email?.trim() || null,
    },
  });
}

/** Bật / tắt tài khoản sale. Tắt không xoá lịch sử bán của người đó. */
export function setSaleAccountActive(userId, isActive) {
  return request(`/api/users/${userId}`, {
    method: 'PATCH',
    body: { is_active: isActive },
  });
}

// ---- Tài liệu ----
export function getDocuments() {
  return request('/api/documents');
}

export function addDocument({ title, description, category, fileUrl, file }) {
  const formData = new FormData();
  formData.append('title', title);
  if (description) formData.append('description', description);
  if (category) formData.append('category', category);
  if (fileUrl) formData.append('file_url', fileUrl);
  if (file) formData.append('file', file);
  return request('/api/documents', { method: 'POST', formData });
}

// ---- Chatbot ----
export function sendChatMessage(message, history) {
  return request('/api/chat', {
    method: 'POST',
    body: { message, history },
  });
}

export { streamChat as streamChatMessage } from './client';

/**
 * Đánh thức lõi AI. Gọi lúc MỞ widget, không chờ kết quả.
 *
 * Gói free của Render cho service ngủ sau 15 phút và dậy lại mất 30-60 giây.
 * Khoảng thời gian khách đọc lời chào rồi soạn câu hỏi vừa đủ để lõi AI dậy
 * xong, nên câu hỏi đầu tiên không lãnh trọn cold start.
 *
 * ⚠️ Phải gọi TỪ TRÌNH DUYỆT, tuyệt đối không nhờ backend gọi hộ. Đo được trên
 * Render: request đi từ trong nền tảng sang URL công khai của một service free
 * đang ngủ trả 502/429 trong dưới 5 giây và KHÔNG đánh thức gì cả, trong khi
 * cùng URL đó gọi từ máy ngoài trả 200 sau ~42 giây. Bản trước nhờ backend làm
 * và nó im lặng không có tác dụng suốt hai ngày.
 *
 * `mode: 'no-cors'` vì ta không cần ĐỌC kết quả, chỉ cần request chạm tới
 * Render để nó dựng container. Nhờ vậy lõi AI không phải khai CORS cho tên miền
 * frontend — request vẫn tới nơi, trình duyệt chỉ giấu phần trả về.
 *
 * Đây là lưới an toàn, KHÔNG phải cơ chế chính. Cơ chế chính là job cron ngoài
 * ping mỗi 5 phút (xem DEPLOY.md); cái này cứu lúc cron chết mà chưa ai biết.
 */
export async function danhThucTroLy() {
  try {
    const suc_khoe = await request('/api/health');
    if (!suc_khoe?.ai_core_url) return null;
    await fetch(`${suc_khoe.ai_core_url}/health`, { mode: 'no-cors', cache: 'no-store' });
  } catch {
    // Hỏng thì chat vẫn chạy, chỉ chờ lâu hơn ở câu đầu.
    return null;
  }
  return null;
}

/**
 * Sửa một ảnh của căn theo yêu cầu bằng lời — tính năng "Modify Object".
 *
 * Trả về data URI, KHÔNG lưu ở server: đây là ảnh minh hoạ do AI tạo cho một
 * tài sản có thật, để lẫn vào ảnh thật là quảng cáo sai sự thật.
 */
/**
 * @param anhNguon Data URI của ảnh AI vừa sinh, để sửa TIẾP trên đó. Bỏ trống
 *   thì server dùng ảnh gốc của căn. Phải gửi lại từ client vì ảnh AI cố ý
 *   không được lưu ở đâu — server không có cách nào tự tìm lại nó.
 */
export function modifyApartmentImage({ maCan, imageId, yeuCau, anhNguon }) {
  return request('/api/images/modify', {
    method: 'POST',
    body: { ma_can: maCan, image_id: imageId, yeu_cau: yeuCau, anh_nguon: anhNguon ?? null },
  });
}

// ---- Lead đặt cọc ----
// Trạng thái CĂN suy ra từ chính bảng lead (migration 010), nên đổi trạng thái
// lead ở đây là căn đổi theo ngay ở cả portal lẫn widget chat.

/** Danh sách lead, mới nhất trước. Chỉ sale và admin gọi được. */
export function getDatCocLeads({ trangThai, maCan } = {}) {
  return request('/api/dat-coc', {
    params: { trang_thai: trangThai, ma_can: maCan },
  });
}

/**
 * Đổi trạng thái một lead.
 *
 * `bo` là VAN XẢ duy nhất: giữ chỗ không tự hết hạn, nên không huỷ ở đây thì
 * căn bị khoá vĩnh viễn và tồn kho khả dụng teo dần mà không ai để ý.
 */
export function doiTrangThaiLead(id, trangThai) {
  return request(`/api/dat-coc/${id}`, {
    method: 'PATCH',
    body: { trang_thai: trangThai },
  });
}

/**
 * Khách bấm "Đặt cọc" trên trang căn hộ. KHÔNG cần đăng nhập.
 *
 * Bắt đăng nhập trước khi để lại số là chặn đúng người đang muốn mua. Widget
 * chat vốn đã ghi lead mà không cần tài khoản, nên nút này không mở thêm bề mặt
 * nào mới.
 */
export function datCoc({ maCan, hoTen, soDienThoai, ghiChu }) {
  return request('/api/dat-coc', {
    method: 'POST',
    body: { ma_can: maCan, ho_ten: hoTen, so_dien_thoai: soDienThoai, ghi_chu: ghiChu },
  });
}

// ---- Tài liệu trợ lý trích dẫn ----
// Khác `getDocuments()` phía trên: cái đó đọc bảng `documents` (tài liệu admin
// tự đăng), còn đây là kho lõi AI thật sự đọc để trả lời. Trích nguồn trỏ vào
// đây, nên nó phải là một bản duy nhất — không sao chép sang Postgres.

/** Danh sách tài liệu trợ lý có thể trích. Phải đăng nhập. */
export function getTaiLieuAI() {
  return request('/api/tai-lieu');
}

/** Toàn văn một tài liệu — đích của nút trích nguồn. */
export function getTaiLieuAIChiTiet(docId) {
  return request(`/api/tai-lieu/${encodeURIComponent(docId)}`);
}

// ---- Tin tức bất động sản ----
/** Lấy tin tức bất động sản mới nhất từ RSS các trang báo. Không cần đăng nhập. */
export function getNews({ limit = 10, refresh = false } = {}) {
  return request('/api/news', {
    params: {
      limit,
      refresh: refresh ? true : undefined,
    },
  });
}

