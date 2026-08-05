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
export function searchApartments({ tower, priceMin, priceMax, type } = {}) {
  return request('/api/apartments', {
    params: {
      tower,
      price_min: priceMin,
      price_max: priceMax,
      type,
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

/** Ghi nhận lượt bán. Không gửi sale_id — backend lấy từ token. */
export function createSale({ maCan, customerName, customerPhone, soldPrice }) {
  return request('/api/sales', {
    method: 'POST',
    body: {
      ma_can: maCan,
      customer_name: customerName || null,
      customer_phone: customerPhone || null,
      sold_price: soldPrice === '' || soldPrice === undefined ? null : Number(soldPrice),
    },
  });
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
