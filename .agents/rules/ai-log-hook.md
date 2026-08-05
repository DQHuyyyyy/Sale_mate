---
description: "AI usage logging is fully automatic — do NOT call any log_* script manually"
activation: always-on
---

# AI Usage Logging — Automatic

Logging prompt vào `.ai-log/session.jsonl` đã được **tự động hoá hoàn toàn**. Bạn (AI agent) **KHÔNG** cần — và **KHÔNG** nên — chạy bất kỳ lệnh logging nào sau mỗi task.

## Cơ chế

Khi student `git push`:
1. Pre-push hook chạy `scripts/log_antigravity.py --auto`, đọc trực tiếp transcript của các conversation Antigravity từ `~/.gemini/antigravity-ide/brain/<conv>/.system_generated/logs/transcript.jsonl` và sweep mọi prompt (`USER_INPUT` + `USER_EXPLICIT`) thuộc về repo hiện tại trong 24 giờ gần nhất.
2. Pre-push hook chạy `scripts/submit_log.py`, đẩy `.ai-log/session.jsonl` lên grading server.

Toàn bộ prompt user đã gõ trong Antigravity IDE được capture **nguyên văn từ disk**, không cần AI tự tóm tắt.

## Không làm những việc sau

- ❌ **KHÔNG** gọi `scripts/log_antigravity.py "<summary>" "<model>"` sau mỗi task. Lệnh này đã bị deprecate; nếu vô tình gọi sẽ tạo log entry giả mạo dạng "TaskComplete" không phải prompt thật của user.
- ❌ **KHÔNG** chạy `scripts/log_manual.py` cho Antigravity — chỉ dùng nó cho ChatGPT / web tool (xem `.agents/workflows/log.md`).
- ❌ **KHÔNG** sửa hoặc xoá file trong `.ai-log/` — chúng được pre-push hook và submit script quản lý.

## Khi nào cần can thiệp

- Nếu pre-push hook báo lỗi → báo lại cho user, đừng tự ý bypass `--no-verify`.
- Nếu student dùng tool không nằm trong list auto-hook (ChatGPT, Gemini Web, v.v.) → trỏ họ tới `.agents/workflows/log.md` để log thủ công.

## Cài đặt một lần sau khi clone repo

### Bước 1 — Cài git pre-push hook

```bash
# Linux / macOS / Git Bash
bash scripts/setup_hooks.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
```

### Bước 2 — Tạo file cấu hình cho AI tool bạn dùng

Các file này **không được commit** — chúng đã nằm trong `.gitignore`. Lý do:
đường dẫn Python, shell và phiên bản tool khác nhau trên từng máy, nên khi bốn
người cùng sửa một file chung thì gần như mọi PR đều dính conflict.

Chỉ tạo file của tool bạn thực sự dùng. Nội dung chuẩn:

<details>
<summary><code>.claude/settings.json</code> — Claude Code</summary>

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=claude", "shell": "bash" } ] }
    ],
    "PostToolUse": [
      { "matcher": ".*", "hooks": [ { "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=claude", "shell": "bash" } ] }
    ]
  }
}
```
</details>

<details>
<summary><code>.codex/hooks.json</code> — Codex</summary>

```json
{
  "description": "Record every Codex user prompt in the project AI log.",
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "name": "log-prompt", "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=codex", "commandWindows": "scripts\\_pyrun.cmd scripts\\log_hook.py --tool=codex", "timeout": 10 } ] }
    ]
  }
}
```
</details>

<details>
<summary><code>.cursor/hooks.json</code> — Cursor</summary>

```json
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [ { "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=cursor" } ],
    "stop": [ { "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=cursor" } ]
  }
}
```
</details>

<details>
<summary><code>.gemini/settings.json</code> — Gemini / Antigravity</summary>

```json
{
  "hooks": {
    "BeforeAgent": [
      { "hooks": [ { "name": "log-prompt", "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=gemini", "timeout": 10000 } ] }
    ],
    "AfterModel": [
      { "matcher": ".*", "hooks": [ { "name": "log-model", "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=gemini", "timeout": 10000 } ] }
    ],
    "SessionEnd": [
      { "matcher": ".*", "hooks": [ { "name": "log-session-end", "type": "command", "command": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=gemini", "timeout": 10000 } ] }
    ]
  }
}
```
</details>

<details>
<summary><code>.github/hooks/hooks.json</code> — GitHub Copilot</summary>

```json
{
  "version": 1,
  "hooks": {
    "userPromptSubmitted": [
      { "type": "command", "bash": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=copilot", "powershell": "scripts\\_pyrun.cmd scripts\\log_hook.py --tool=copilot", "timeoutSec": 10 }
    ],
    "sessionEnd": [
      { "type": "command", "bash": "bash scripts/_pyrun.sh scripts/log_hook.py --tool=copilot", "powershell": "scripts\\_pyrun.cmd scripts\\log_hook.py --tool=copilot", "timeoutSec": 10 }
    ]
  }
}
```
</details>

### Bước 3 — Điền `AI_LOG_SERVER` trong `.env`

## Script trong `scripts/` là hạ tầng dùng chung — đóng băng

`_pyrun.sh` · `_pyrun.cmd` · `log_hook.py` · `log_manual.py` · `log_antigravity.py`
· `submit_log.py` · `setup_hooks.ps1` · `setup_hooks.sh`

Tám file này vẫn được commit vì clone mới phải dựng lại được cơ chế log. Nhưng
**đừng sửa chúng trong PR tính năng**. Máy bạn chạy không được thì báo cả nhóm
rồi mở PR riêng — đã có ba người vá cùng một bug trên ba nhánh khác nhau, và
lần nào cũng phải giải conflict thủ công.
