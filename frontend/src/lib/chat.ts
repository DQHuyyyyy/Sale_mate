/**
 * Client đọc SSE từ POST /api/v1/chat/stream.
 *
 * Dùng fetch + ReadableStream chứ không dùng EventSource, vì EventSource chỉ
 * gửi được GET còn ta cần POST kèm body (câu hỏi + lịch sử).
 */

import { API_BASE } from "@/lib/api";
import type { ChatEvent, ChatMessage } from "@/lib/types";

export interface StreamOptions {
  message: string;
  sessionId?: string;
  history?: ChatMessage[];
  signal?: AbortSignal;
}

/** Phát từng ChatEvent theo thứ tự backend gửi về. */
export async function* streamChat(
  options: StreamOptions,
): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: options.message,
      session_id: options.sessionId ?? null,
      history: options.history ?? [],
    }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Máy chủ trả về ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Mỗi message SSE kết thúc bằng một dòng trống.
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const payload = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("");

      if (!payload) continue;

      try {
        yield JSON.parse(payload) as ChatEvent;
      } catch {
        console.error("Không đọc được event SSE:", payload);
      }
    }
  }
}
