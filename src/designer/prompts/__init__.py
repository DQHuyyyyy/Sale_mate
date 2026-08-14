"""Nạp prompt sửa ảnh từ file .md kèm version.

Cùng nếp với `src/agents/prompts/`: prompt để ở file riêng, không hardcode trong
code, để đổi prompt là một diff đọc được và còn so sánh được trước/sau.

`sua_anh_*.md` chia thành nhiều khối theo tiêu đề `## <tên>`. Lý do: dặn model
xoá một vật thể khác hẳn dặn nó đổi màu vật thể đó, mà cả hai lại dùng chung một
bộ quy tắc "không được làm vỡ ảnh". Tách khối cho phép sửa từng loại thao tác mà
không đụng phần chung, và không phải sinh ra ba file gần giống nhau.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent

DINH_VI_VERSION = "v1"
SUA_ANH_VERSION = "v1"

_TIEU_DE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@lru_cache
def load_prompt(name: str) -> str:
    """Đọc nguyên nội dung một prompt theo tên file (không cần đuôi .md)."""
    path = _PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_khoi(name: str) -> dict[str, str]:
    """Tách file .md thành dict {tên khối: nội dung} theo tiêu đề `## `.

    Phần đứng trước tiêu đề đầu tiên bị bỏ — đó là ghi chú cho người đọc file,
    không phải nội dung gửi model.

    Không cache: trả về dict mới mỗi lần để bên gọi lỡ sửa cũng không làm hỏng
    prompt của lượt sau. Việc đọc file đã được `load_prompt` cache rồi.
    """
    noi_dung = load_prompt(name)
    moc = list(_TIEU_DE.finditer(noi_dung))

    return {
        m.group(1).strip(): noi_dung[m.end() : moc[i + 1].start() if i + 1 < len(moc) else len(noi_dung)].strip()
        for i, m in enumerate(moc)
    }


def prompt_dinh_vi() -> str:
    """System prompt cho model thị giác: khoanh vùng + chặn yêu cầu mơ hồ."""
    return load_prompt(f"dinh_vi_{DINH_VI_VERSION}")


def khoi_sua_anh() -> dict[str, str]:
    """Các khối quy tắc gửi model sinh ảnh, tra theo tên thao tác."""
    return load_khoi(f"sua_anh_{SUA_ANH_VERSION}")


__all__ = [
    "DINH_VI_VERSION",
    "SUA_ANH_VERSION",
    "khoi_sua_anh",
    "load_khoi",
    "load_prompt",
    "prompt_dinh_vi",
]
