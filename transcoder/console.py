import logging
import os
import sys
from typing import Optional, TextIO


ANSI_RESET = "\033[0m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_DIM = "\033[2m"


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
