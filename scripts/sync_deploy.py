"""Đẩy nhánh cần deploy từ repo BTC sang mirror cá nhân cho Render và Vercel.

Chạy qua `make sync-deploy`, hoặc trực tiếp:

    .venv/Scripts/python.exe scripts/sync_deploy.py [ten-remote]

Viết bằng Python thay vì recipe shell vì `make` trên Windows chạy recipe bằng
cmd.exe khi không tìm thấy sh.exe — cú pháp POSIX sẽ vỡ. Python thì giống nhau
ở PowerShell, cmd, Git Bash và Linux.
"""

from __future__ import annotations

import subprocess
import sys

# Mirror chỉ giữ đúng những nhánh đang được deploy. Hiện chỉ có một môi trường,
# chạy từ develop — đó cũng là nhánh mặc định của repo mirror.
#
# Phân cấp main <- develop vẫn giữ nguyên ở repo BTC. Đẩy cả main sang mirror
# chỉ tổ hại: main đang là bản cũ chưa có thư mục interface/, Render và Vercel
# trỏ vào đó là build hỏng.
#
# Khi nào dựng môi trường production thì thêm "main" vào tuple này.
BRANCHES = ("develop",)
DEFAULT_REMOTE = "deploy"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    """Chạy git, trả CompletedProcess. Không raise — nơi gọi tự quyết định."""
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def remote_url(remote: str) -> str | None:
    result = git("remote", "get-url", remote)
    return result.stdout.strip() if result.returncode == 0 else None


def ref_exists(ref: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", ref).returncode == 0


def commits_behind(mirror_ref: str, source_ref: str) -> int:
    result = git("rev-list", "--count", f"{mirror_ref}..{source_ref}")
    return int(result.stdout.strip() or 0) if result.returncode == 0 else -1


def push(remote: str, branch: str) -> bool:
    """Đẩy thẳng origin/<branch> sang mirror, không qua nhánh local.

    Nhờ vậy kết quả không phụ thuộc việc đã checkout hay pull nhánh đó chưa —
    luôn là đúng thứ đang nằm trên repo BTC.
    """
    result = git("push", remote, f"refs/remotes/origin/{branch}:refs/heads/{branch}")
    if result.returncode != 0:
        print(f"     LỖI: {result.stderr.strip()}")
    return result.returncode == 0


def sync_branch(remote: str, branch: str) -> bool:
    """Trả về False nếu có lỗi thật sự; nhánh thiếu ở repo BTC không tính lỗi."""
    if not ref_exists(f"origin/{branch}"):
        print(f"  {branch}: không có trên repo BTC, bỏ qua")
        return True

    if not ref_exists(f"{remote}/{branch}"):
        print(f"  {branch}: mirror chưa có nhánh này, đẩy lần đầu...")
        return push(remote, branch)

    behind = commits_behind(f"{remote}/{branch}", f"origin/{branch}")
    if behind == 0:
        print(f"  {branch}: đã đồng bộ")
        return True

    print(f"  {branch}: mirror thiếu {behind} commit, đang đẩy...")
    return push(remote, branch)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    remote = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REMOTE

    url = remote_url(remote)
    if url is None:
        print(f"Chưa có remote '{remote}'. Chạy một lần:")
        print(f"  git remote add {remote} <url-repo-mirror>")
        return 1

    print(f"Mirror: {url}")
    git("fetch", "--quiet", "--prune", "origin")
    git("fetch", "--quiet", "--prune", remote)

    ok = all([sync_branch(remote, b) for b in BRANCHES])
    if not ok:
        print("Có nhánh chưa đẩy được — xem lỗi ở trên.")
        return 1

    print("Xong. Render sẽ tự build lại nhánh nào vừa thay đổi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
