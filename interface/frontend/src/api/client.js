// Client HTTP dùng chung. Mọi lời gọi backend đều đi qua đây — tự gắn
// Authorization, tự dịch lỗi sang tiếng Việt.
//
// Frontend KHÔNG gọi thẳng OpenAI hay Supabase. Ảnh chỉ nhận URL do backend trả.

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const TOKEN_KEY = 'salesmate_token';

let onUnauthorized = null;

/** Đăng ký hành động khi token hết hạn (AuthContext dùng để đá về /login). */
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function buildUrl(path, params) {
  const url = `${BASE_URL}${path}`;
  if (!params) return url;

  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value);
    }
  });
  const queryString = query.toString();
  return queryString ? `${url}?${queryString}` : url;
}

async function readError(response) {
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') return data.detail;
    // Lỗi validate của FastAPI: detail là mảng.
    if (Array.isArray(data.detail) && data.detail.length) {
      return data.detail.map((item) => item.msg).join('. ');
    }
  } catch {
    // Không phải JSON — rơi xuống thông báo mặc định bên dưới.
  }
  return 'Không gọi được máy chủ. Kiểm tra kết nối rồi thử lại.';
}

export async function request(path, { method = 'GET', body, params, formData } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new ApiError('Không kết nối được máy chủ. Kiểm tra backend đã chạy chưa.', 0);
  }

  if (response.status === 401) {
    setToken(null);
    if (onUnauthorized) onUnauthorized();
    throw new ApiError('Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.', 401);
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }

  if (response.status === 204) return null;
  return response.json();
}
