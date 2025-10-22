"""
Logger configuration for the semcod project.

This module configures structlog with sane defaults so both library
consumers and CLI/API entry points can share consistent logging.
"""
from __future__ import annotations

import logging
from typing import Optional

import structlog


def _configure_structlog() -> None:
    """Initialize structlog with console-friendly formatting."""
    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(colors=False),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure global logging.

    Parameters
    ----------
    level:
        Base logging level for the root logger.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _configure_structlog()


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Retrieve a structlog logger with the provided name."""
    return structlog.get_logger(name)
