"""Cửa sổ trượt đếm trong bộ nhớ tiến trình.

Chép nguyên cơ chế của `interface/backend/app/core/ratelimit.py`. Hai service
tách nhau nên không import chung được — cùng lý do `chuan_hoa_sdt` tồn tại hai
bản. Khác nhau ở chỗ DÙNG chứ không ở chỗ đếm: bên portal khoá theo người gọi
(có danh tính), bên này khoá theo cả tiến trình (xem `src/api/bao_ve.py`).

Hai giới hạn phải biết trước khi tin vào con số:

- Nhiều worker uvicorn thì mỗi worker đếm riêng, trần thực tế nhân theo số worker.
- Khởi động lại là bộ đếm về 0. Render free ngủ sau 15 phút không có request.

Cần chặt hơn thì chuyển sang Redis, giữ nguyên chữ ký `check`.
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
            # Dọn key rỗng để dict không phình theo số khoá đã từng ghé.
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0

    def reset(self) -> None:
        """Xoá sạch bộ đếm. Chỉ dùng trong test — mỗi ca phải khởi đầu như nhau."""
        with self._lock:
            self._hits.clear()
