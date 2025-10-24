"""
Logger configuration for the semcode project.

This module integrates structlog with the standard logging module so CLI/API
entry points can choose between silent stdout or rich console/file output.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import structlog
from structlog.stdlib import BoundLogger, ProcessorFormatter
from structlog.typing import Processor

_PRE_CHAIN: tuple[Processor, ...] = (
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.TimeStamper(fmt="iso"),
)


def _configure_structlog(min_level: int) -> None:
    """Bridge structlog into the standard logging framework."""
    structlog.configure(
        processors=_PRE_CHAIN + (ProcessorFormatter.wrap_for_formatter,),
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _build_formatter(renderer: Processor) -> ProcessorFormatter:
    return ProcessorFormatter(processor=renderer, foreign_pre_chain=_PRE_CHAIN)


def configure_logging(
    level: int = logging.INFO,
    enable_console: bool = True,
    console_level: int | None = None,
) -> None:
    """
    Configure global logging.

    Parameters
    ----------
    level:
        Base logging level for the root logger.
    enable_console:
        When False, suppress log emission to stdout/stderr.
    console_level:
        Severity threshold for messages emitted to stdout/stderr. Defaults to ``level``.
    """
    _configure_structlog(level)
    logging.captureWarnings(True)

    handlers: list[logging.Handler] = []

    if enable_console:
        handler = logging.StreamHandler()
        handler.setLevel(console_level if console_level is not None else level)
        handler.setFormatter(
            _build_formatter(structlog.dev.ConsoleRenderer(colors=False))
        )
        handlers.append(handler)
    else:
        handlers.append(logging.NullHandler())

    logging.basicConfig(level=level, handlers=handlers, force=True)


def get_logger(name: Optional[str] = None) -> BoundLogger:
    """Retrieve a structlog logger with the provided name."""
    return structlog.get_logger(name)


def redirect_logging_to_file(path: Path) -> None:
    """Redirect standard logging output to the given file."""
    _configure_structlog(logging.INFO)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(_build_formatter(structlog.dev.ConsoleRenderer(colors=False)))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
