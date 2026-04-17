import logging
import os
import sys
from typing import Optional, TextIO


ANSI_RESET = "\033[0m"
ANSI_BLUE = "\033[94m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_GRAY = "\033[90m"
ANSI_DIM = "\033[2m"
ANSI_BOLD = "\033[1m"


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def init_console() -> None:
    if os.name == "nt":
        # 在 Windows 终端中启用 ANSI 转义支持。
        os.system("")


def ensure_text_output_encoding() -> None:
    """Best-effort 设置标准输出编码，避免非 UTF-8 终端下中文输出崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue

        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue

        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                reconfigure(errors="replace")
            except Exception:
                # 某些受限运行环境可能不允许重新配置，忽略并继续。
                pass


def supports_color_output(stream: Optional[TextIO] = None) -> bool:
    if os.getenv("NO_COLOR"):
        return False
    target = stream or sys.stdout
    checker = getattr(target, "isatty", None)
    if checker is None:
        return False
    return bool(checker())


def colorize(text: str, color_code: str, stream: Optional[TextIO] = None) -> str:
    if not supports_color_output(stream=stream):
        return text
    return f"{color_code}{text}{ANSI_RESET}"


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: ANSI_DIM,
        logging.INFO: ANSI_GREEN,
        logging.WARNING: ANSI_YELLOW,
        logging.ERROR: ANSI_RED,
        logging.CRITICAL: ANSI_RED,
    }

    def __init__(self, fmt: str, stream: Optional[TextIO] = None):
        super().__init__(fmt)
        self._stream = stream

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = self.LEVEL_COLORS.get(record.levelno)
        if not color:
            return message
        return colorize(message, color, stream=self._stream)
