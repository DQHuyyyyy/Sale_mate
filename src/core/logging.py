"""Structured logging dạng JSON.

Log JSON để sau này đẩy thẳng vào công cụ giám sát mà không phải parse text.
Không bao giờ log giá trị nhạy cảm (API key, mật khẩu, token).
"""

from __future__ import annotations

import json
import logging
import sys
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

_NOISY_LIBRARIES = ("httpx", "httpcore", "urllib3", "openai", "qdrant_client")

# Context của lượt hỏi hiện tại, tự động gắn vào mọi dòng log trong lượt đó.
# Dùng ContextVar chứ không dùng biến toàn cục: mỗi request async có bản riêng,
# hai người hỏi cùng lúc không trộn log của nhau.
trace_context: ContextVar[dict[str, Any]] = ContextVar("trace_context", default={})


@contextmanager
def trace(**fields: Any) -> Iterator[None]:
    """Gắn các trường này vào mọi log phát ra bên trong khối.

    Dùng:
        with trace(session_id=sid):
            ...   # mọi log ở đây đều có session_id
    """
    token = trace_context.set({**trace_context.get(), **fields})
    try:
        yield
    finally:
        trace_context.reset(token)


class JSONFormatter(logging.Formatter):
    """Đưa mỗi bản ghi log thành một dòng JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Gộp context của lượt hỏi (session_id) với context riêng của dòng log.
        # Nhờ vậy lọc log theo một session là thấy đủ đường đi của câu hỏi đó:
        # router → tools → retrieve → generate, kèm thời gian từng chặng.
        context = {**trace_context.get(), **(getattr(record, "context", None) or {})}
        if context:
            entry["context"] = context

        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Một dòng gọn cho người đọc trên terminal.

    Vì sao cần cả hai định dạng: JSON tốt cho công cụ giám sát nhưng đọc bằng mắt
    thì không nổi — mỗi bước của agent thành một khối `{"timestamp": ...}` dài,
    và câu hỏi "agent vừa chọn tool nào" chìm nghỉm giữa chúng. Dev cần thấy
    ĐƯỜNG ĐI; production cần dữ liệu parse được. Hai nhu cầu khác nhau, hai
    định dạng.

    Không dùng màu ANSI: log hay bị chuyển hướng vào file hoặc `grep`, và mã màu
    lọt vào đó gây nhiễu nhiều hơn là giúp.
    """

    # Nhãn ngắn cho từng bước, canh đều để mắt dò theo cột.
    _RONG_NHAN = 11

    def format(self, record: logging.LogRecord) -> str:
        context = {**trace_context.get(), **(getattr(record, "context", None) or {})}
        gio = datetime.now().strftime("%H:%M:%S")

        # `buoc` là nhãn của một chặng trong lượt hỏi. Có thì hiện thành cột
        # riêng để đọc dọc; không có thì rơi về tên module.
        nhan = str(context.pop("buoc", None) or record.name.rsplit(".", 1)[-1])
        muc = record.levelname[0]

        phan = [f"{gio} {muc} {nhan:<{self._RONG_NHAN}} {record.getMessage()}"]

        # `session_id` lặp lại ở mọi dòng nên rút còn 6 ký tự đầu — đủ để phân
        # biệt hai người hỏi cùng lúc mà không chiếm hết bề ngang.
        sid = context.pop("session_id", None)
        chi_tiet = " ".join(f"{k}={_gon(v)}" for k, v in context.items() if v not in (None, "", [], {}))
        if chi_tiet:
            phan.append(f"  {chi_tiet}")
        if sid:
            phan.append(f"  [{str(sid)[:6]}]")

        dong = "".join(phan)
        if record.exc_info and record.exc_info[0] is not None:
            dong += f"\n    {record.exc_info[0].__name__}: {record.exc_info[1]}"
        return dong


def _gon(gia_tri: Any) -> str:
    """Rút gọn giá trị để một dòng log không tràn màn hình."""
    if isinstance(gia_tri, float):
        return f"{gia_tri:.3f}"
    if isinstance(gia_tri, list | tuple):
        return ",".join(str(x) for x in gia_tri)[:60] or "-"
    van_ban = str(gia_tri)
    return van_ban if len(van_ban) <= 60 else van_ban[:57] + "…"


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler không bao giờ làm sập app vì lỗi mã hoá.

    Vì sao cần: log của hệ thống này toàn tiếng Việt. Nếu stdout không phải UTF-8
    (console Windows cp1252, hoặc stream đã bị wrap trong Docker/CI), việc ghi
    log sẽ ném UnicodeEncodeError — tức là chính công cụ chẩn đoán lại trở thành
    nguồn lỗi. Ở đây ta lùi về dạng ASCII-escaped (\\uXXXX): xấu mắt hơn nhưng
    vẫn là JSON hợp lệ và không mất thông tin.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                message = self.format(record)
                escaped = message.encode("unicode_escape").decode("ascii")
                self.stream.write(escaped + self.terminator)
                self.flush()
            except Exception:  # noqa: BLE001 - log hỏng thì thôi, đừng làm sập app
                self.handleError(record)


class NhatKyPhienHandler(logging.Handler):
    """Ghi log của MỖI PHIÊN trò chuyện ra một file JSON Lines riêng.

    Vì sao tách khỏi terminal: terminal cần ngắn để đọc lướt lúc đang thao tác,
    còn chẩn đoán một câu trả lời sai lại cần đủ chi tiết và cần xem lại được
    sau vài giờ. Hai nhu cầu ngược nhau, không nhét chung một chỗ được.

    Một file một phiên, tên theo thời điểm phiên bắt đầu — mở thư mục ra là thấy
    ngay lượt trò chuyện nào lúc mấy giờ, không phải grep giữa một file chung.

    Dạng JSON Lines (mỗi dòng một object) chứ không phải một mảng JSON: ghi bằng
    cách nối thêm dòng nên không phải đọc lại và ghi đè cả file, và file dở dang
    khi tiến trình bị giết vẫn đọc được tới dòng cuối cùng.

    Dòng log KHÔNG có `session_id` bị bỏ qua — chúng thuộc về khởi động ứng dụng
    hay lệnh CLI, không thuộc phiên nào cả.
    """

    # Giữ vài file mở sẵn để khỏi mở/đóng theo từng dòng. Vượt số này thì đóng
    # file ít dùng nhất; phiên đó quay lại vẫn ghi tiếp vào ĐÚNG file cũ nhờ
    # `_ten_file` nhớ tên riêng.
    _GIU_MO_TOI_DA = 8
    # Chặn rò rỉ bộ nhớ trên server chạy lâu: chỉ nhớ tên file của các phiên gần
    # đây. Phiên cũ quay lại sau khi bị quên sẽ sang file mới — hiếm, và chấp
    # nhận được so với việc giữ một dict lớn dần mãi.
    _NHO_TEN_TOI_DA = 512

    def __init__(self, thu_muc: str | Path) -> None:
        super().__init__(level=logging.DEBUG)
        self._thu_muc = Path(thu_muc)
        self._ten_file: OrderedDict[str, Path] = OrderedDict()
        self._dang_mo: OrderedDict[str, TextIO] = OrderedDict()
        self.setFormatter(JSONFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        phien = (trace_context.get() or {}).get("session_id")
        if not phien:
            return
        try:
            tep = self._lay_tep(str(phien))
            tep.write(self.format(record) + "\n")
            tep.flush()
        except Exception:  # noqa: BLE001 - ghi log hỏng thì thôi, đừng làm sập app
            self.handleError(record)

    def _lay_tep(self, phien: str) -> TextIO:
        if phien in self._dang_mo:
            self._dang_mo.move_to_end(phien)
            return self._dang_mo[phien]

        self._thu_muc.mkdir(parents=True, exist_ok=True)
        duong_dan = self._ten_file.get(phien)
        if duong_dan is None:
            luc = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            duong_dan = self._thu_muc / f"{luc}_{phien[:8]}.jsonl"
            self._ten_file[phien] = duong_dan
            while len(self._ten_file) > self._NHO_TEN_TOI_DA:
                self._ten_file.popitem(last=False)

        tep = duong_dan.open("a", encoding="utf-8")
        self._dang_mo[phien] = tep
        while len(self._dang_mo) > self._GIU_MO_TOI_DA:
            _, cu = self._dang_mo.popitem(last=False)
            cu.close()
        return tep

    def close(self) -> None:
        for tep in self._dang_mo.values():
            tep.close()
        self._dang_mo.clear()
        super().close()


def setup_logging(level: str = "INFO", dinh_dang: str = "auto", thu_muc_nhat_ky: str | None = None) -> None:
    """Cấu hình root logger. Gọi một lần lúc app khởi động.

    `dinh_dang`:
        auto  — text khi chạy trên terminal thật, json khi bị chuyển hướng.
        text  — ép dạng người đọc.
        json  — ép dạng máy đọc.

    Mặc định `auto` vì nó đúng trong cả hai hoàn cảnh mà không ai phải nhớ cấu
    hình: gõ `make run-ai` ở terminal thì thấy đường đi của agent; chạy trong
    Docker hay đẩy vào file thì ra JSON cho công cụ giám sát.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for existing in list(root.handlers):
        root.removeHandler(existing)

    # Console Windows mặc định là cp1252, không mã hoá được tiếng Việt và làm
    # chính hệ thống log đổ lỗi UnicodeEncodeError. Ép UTF-8 cho chắc.
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # stream đã bị thay bằng thứ không đổi được
            pass

    if dinh_dang == "auto":
        dinh_dang = "text" if getattr(stream, "isatty", lambda: False)() else "json"

    handler = SafeStreamHandler(stream)
    handler.setFormatter(TextFormatter() if dinh_dang == "text" else JSONFormatter())
    root.addHandler(handler)

    # File nhận DEBUG bất kể terminal đặt mức nào: chỗ này để xem lại về sau,
    # mà lúc cần xem lại thì không quay ngược thời gian bật thêm mức log được.
    # Muốn thế thì root phải ở DEBUG, còn handler terminal tự lọc theo `level`.
    if thu_muc_nhat_ky:
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        root.setLevel(logging.DEBUG)
        root.addHandler(NhatKyPhienHandler(thu_muc_nhat_ky))

    for name in _NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Lấy logger cho một module. Dùng: logger = get_logger(__name__)."""
    return logging.getLogger(name)


def log_context(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Ghi log kèm dữ liệu có cấu trúc.

    Ví dụ:
        log_context(logger, logging.INFO, "Chat bắt đầu", session_id=sid, chars=len(msg))
    """
    logger.log(level, message, extra={"context": fields})
