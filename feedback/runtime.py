"""The feedback stores, made once per process (each borrows the shared pool,
``core/store.shared_engine``). A test sets them with ``use``."""

from __future__ import annotations

from typing import Any

_FEEDBACK: Any = None
_SURVEYS: Any = None


def feedback_store(settings: Any) -> Any:
    global _FEEDBACK
    if _FEEDBACK is None:
        from .store import make_feedback_store

        _FEEDBACK = make_feedback_store(settings)
    return _FEEDBACK


def survey_store(settings: Any) -> Any:
    global _SURVEYS
    if _SURVEYS is None:
        from surveys.store import make_survey_store

        _SURVEYS = make_survey_store(settings)
    return _SURVEYS


def use(*, feedback: Any = None, surveys: Any = None) -> None:
    """For tests: the in-memory stores."""
    global _FEEDBACK, _SURVEYS
    _FEEDBACK, _SURVEYS = feedback, surveys
