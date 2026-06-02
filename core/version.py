"""Single source of truth for the app version.

Read from ``pyproject.toml`` so the version is declared in exactly one place
and surfaced everywhere else (the FastAPI app, ``/healthz``, and the page
footer) without drift.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _read_version() -> str:
    try:
        return tomllib.loads(_PYPROJECT.read_text())["project"]["version"]
    except Exception:  # pragma: no cover - defensive; pyproject is always shipped
        return "0.0.0"


__version__ = _read_version()
