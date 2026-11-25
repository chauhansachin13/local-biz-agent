import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from config.settings import settings

_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class ColoredStructuredFormatter(logging.Formatter):
    """Formatter producing colored console logs with optional structured key-value context."""

    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    LEVEL_COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }

    def __init__(self, use_color: bool = True) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        level_name = f"{record.levelname:<8}"
        message = record.getMessage()

        extra_fields: dict[str, Any] = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
        }
        context_str = (
            f" | {json.dumps(extra_fields, default=str, ensure_ascii=False)}"
            if extra_fields
            else ""
        )

        if self.use_color:
            color = self.LEVEL_COLORS.get(record.levelno, "")
            formatted = (
                f"{self.DIM}{timestamp}{self.RESET} "
                f"{color}{self.BOLD}{level_name}{self.RESET} "
                f"{self.DIM}[{record.name}]{self.RESET} "
                f"{message}{self.DIM}{context_str}{self.RESET}"
            )
        else:
            formatted = f"{timestamp} {level_name} [{record.name}] {message}{context_str}"

        if record.exc_info:
            formatted = f"{formatted}\n{self.formatException(record.exc_info)}"
        return formatted


def _resolve_log_level(level_name: str) -> int:
    level = logging.getLevelName(level_name.upper())
    return level if isinstance(level, int) else logging.INFO


def get_logger(name: str) -> logging.Logger:
    """Return a configured structured logger with colored console output."""
    logger = logging.getLogger(name)
    target_level = _resolve_log_level(settings.log_level)
    logger.setLevel(target_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(target_level)
        use_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        handler.setFormatter(ColoredStructuredFormatter(use_color=use_color or True))
        logger.addHandler(handler)
        logger.propagate = False

    return logger
