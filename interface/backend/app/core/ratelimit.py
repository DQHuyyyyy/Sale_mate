"""Giới hạn số lượt gọi, dùng cho endpoint công khai.

Cửa sổ trượt, đếm trong bộ nhớ tiến trình. Đủ cho quy mô hiện tại nhưng có hai
giới hạn phải biết:

- Chạy nhiều worker uvicorn thì mỗi worker đếm riêng, hạn mức thực tế nhân lên
  theo số worker.
- Khởi động lại backend là bộ đếm về 0.

Cần chặt hơn thì chuyển sang Redis, giữ nguyên hàm `check` này.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Ghi nhận một lượt gọi.

        Trả (còn lượt hay không, số giây phải đợi nếu hết lượt).
        """
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()

            if len(hits) >= self.max_calls:
                cho_them = self.window_seconds - (now - hits[0])
                return False, max(1, int(cho_them) + 1)

            hits.append(now)
            # Dọn key rỗng để dict không phình theo số IP đã từng ghé.
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0
