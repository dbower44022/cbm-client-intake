"""Shared logging configuration for BOTH processes (web tier and worker).

Before this existed (reliability review 2026-07-17, logging section), the two
processes diverged: ``core/app.py``'s format omitted the logger name (no module
attribution, no way to filter httpx noise) and had minute-resolution
timestamps, while the worker's separate ``basicConfig`` used the stdlib default
— worker lines had NO timestamps at all, so retry forensics depended on the DO
console clock. One helper, one format, and a runtime ``LOG_LEVEL`` lever
(default INFO — e.g. DEBUG exposes the comms triage decisions without a
deploy).
"""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging: level + name + seconds-precision timestamp.

    Safe to call repeatedly: the handler/format is installed only when the
    root logger has none yet (so a re-call — or pytest's caplog handler —
    is never clobbered); the LEVEL is (re)applied on every call, which is
    how the configured ``LOG_LEVEL`` takes effect after the import-time
    default call.
    """
    resolved = getattr(logging, (level or "INFO").upper(), None)
    if not isinstance(resolved, int):
        resolved = logging.INFO
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            format="%(levelname)s: %(asctime)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    root.setLevel(resolved)
