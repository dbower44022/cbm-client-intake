"""Single source of truth for the app version, and for the release stamp.

The version is read from ``pyproject.toml`` so it is declared in exactly one
place and surfaced everywhere else (the FastAPI app, ``/healthz``, and the page
footer) without drift.

**The release stamp (chapter network, Stamp A)** answers a different question:
``version`` says *what code is this*, ``releaseTag`` says *what promotion is
this*. It lives in ``release-tag.txt`` at the repository root, written by
``scripts/cut_release.sh`` into the very commit the tag names, because a
container has no ``.git`` and the tag has to travel in the source. It used to
travel instead as a ``RUN_AND_BUILD_TIME`` variable in every deployment's spec,
which made promoting a deployment two operations rather than one and, when only
half of it was done, made a deployment report the *previous* promotion as if it
were the new one.

**The stamp counts only when the code is exactly that release.** The cut writes
``v<version>`` at the commit where ``pyproject.toml`` declares that version, so
the two agree at the tagged commit and nowhere else: the next commit bumps the
version and the stamp stops applying. That is what keeps the soak copy (which
tracks ``main``) reporting no release rather than the last one that went past,
and it is the same principle the release-train plan states — reporting a previous
promotion as if it were current is worse than reporting none.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _ROOT / "pyproject.toml"
_RELEASE_STAMP = _ROOT / "release-tag.txt"


def _read_version() -> str:
    try:
        return tomllib.loads(_PYPROJECT.read_text())["project"]["version"]
    except Exception:  # pragma: no cover - defensive; pyproject is always shipped
        return "0.0.0"


__version__ = _read_version()


def _read_stamp_file() -> str:
    """The raw tag in ``release-tag.txt``: first non-blank, non-comment line."""
    try:
        for line in _RELEASE_STAMP.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
    except OSError:  # the file is absent on an old checkout, or unreadable
        return ""
    return ""


def release_stamp(version: str | None = None) -> str:
    """The release tag this build IS, or ``""`` when it is not a release.

    Empty whenever the stamp does not name this exact version — an untagged
    build, a commit after the cut, or a hotfix that never went through the
    train. Deliberately not "the last tag we saw".
    """
    stamped = _read_stamp_file()
    if not stamped:
        return ""
    return stamped if stamped == f"v{version or __version__}" else ""
