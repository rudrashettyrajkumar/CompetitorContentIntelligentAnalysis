"""structlog setup: JSON in production, pretty console for dev/tests."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO", json_output: bool | None = None) -> None:
    if json_output is None:
        json_output = not sys.stderr.isatty()

    logging.basicConfig(level=level.upper(), stream=sys.stderr, format="%(message)s")

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
