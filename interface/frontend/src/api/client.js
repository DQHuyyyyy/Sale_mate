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

/**
 * Hỏi trợ lý theo kiểu stream — chữ hiện dần thay vì đợi cả đoạn rồi mới hiện.
 *
 * Dùng `fetch` chứ không dùng `EventSource`: EventSource chỉ gửi được GET, mà
 * câu hỏi kèm lịch sử hội thoại phải nằm trong body POST.
 *
 * `onEvent(event)` được gọi cho từng event lõi AI phát ra:
 *   start · route (tiến trình suy luận) · token · sources · done · error
 */
export async function streamChat(message, history, onEvent, signal, sessionId) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(buildUrl('/api/chat/stream'), {
      method: 'POST',
      headers,
      // session_id gửi lại để log của cả cuộc trò chuyện gom về một ID, thay vì
      // mỗi lượt một ID khác. Lượt đầu chưa có thì bỏ trống, lõi AI tự sinh.
      body: JSON.stringify({ message, history, session_id: sessionId ?? null }),
      signal,
    });
  } catch {
    throw new ApiError('Không kết nối được máy chủ. Kiểm tra backend đã chạy chưa.', 0);
  }

  if (!response.ok || !response.body) {
    throw new ApiError(await readError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE ngăn hai event bằng một DÒNG TRỐNG, mà dòng trống đó có thể là
    // "\n\n" hoặc "\r\n\r\n" tuỳ server. sse-starlette (lõi AI) dùng CRLF, nên
    // tách bằng "\n\n" là không khớp gì cả: buffer phình mãi, không event nào
    // được phát, và stream kết thúc lặng lẽ không token không lỗi.
    const parts = buffer.split(/\r?\n\r?\n/);
    // Phần đuôi có thể chưa trọn vẹn — chunk mạng cắt ở đâu cũng được.
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      const dataLine = part.split(/\r?\n/).find((line) => line.startsWith('data:'));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(5).trim()));
      } catch {
        // Một event hỏng thì bỏ qua nó, không làm đứt cả câu trả lời.
      }
    }
  }
}
