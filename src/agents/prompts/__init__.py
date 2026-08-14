"""Nạp prompt từ file .md kèm version.

Prompt để ở file riêng (không hardcode trong code) để đổi prompt là một diff
đọc được, và để chạy eval so sánh trước/sau khi đổi.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent

SYSTEM_PROMPT_VERSION = "v4"


@lru_cache
def load_prompt(name: str) -> str:
    """Đọc nội dung một prompt theo tên file (không cần đuôi .md)."""
    path = _PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def system_prompt() -> str:
    """System prompt đang dùng cho câu trả lời cuối."""
    return load_prompt(f"system_{SYSTEM_PROMPT_VERSION}")


__all__ = ["SYSTEM_PROMPT_VERSION", "load_prompt", "system_prompt"]
