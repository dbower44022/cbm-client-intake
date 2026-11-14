"""Business Evaluation's survey definitions (plan § 2, ruling BE9), on the
survey engine's format (``surveys/definitions.py``, ruling BE23).

One survey per file, ``evaluation/surveys/<key>.v<n>.yaml``. A file is never
edited once a client has answered it: a changed question is a new version, so
every Business Evaluation record names the exact questions its answers belong
to (``surveyVersion``, such as ``finance.v1``).

What Business Evaluation adds to the engine's format:

    area: Finance                # the CRM's evaluationArea value; absent on
                                 # the business profile, which is not an area

and one rule: the business profile survey must exist.
``tests/test_evaluation_surveys.py`` fails on an invalid file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from surveys import definitions as _engine
from surveys.definitions import (  # noqa: F401 — Business Evaluation's names for them
    CHOICE_TYPES, QUESTION_TYPES, Question, Section, SurveyError, latest,
)

SURVEY_DIR = Path(__file__).resolve().parent / "surveys"

# The business profile is answered once per engagement (ruling BE8).
PROFILE_KEY = "business-profile"

AREAS = ("Finance", "Competition", "Marketing", "Funding", "Product", "Information Technology")


@dataclass(frozen=True)
class Survey(_engine.Survey):
    """An engine survey with its evaluation area ("" on the business profile)."""

    area: str = ""


def _check(raw: dict, where: str) -> None:
    area = raw.get("area") or ""
    if raw["key"] == PROFILE_KEY:
        if area:
            raise SurveyError(f"{where}: the business profile is not an evaluation area")
    elif area not in AREAS:
        raise SurveyError(f"{where}: area {area!r} is not one of {', '.join(AREAS)}")


RULES = _engine.LoaderRules(extra_keys=("area",), survey_class=Survey, check=_check,
                            required_keys=(PROFILE_KEY,))


def parse(path: Path) -> Survey:
    """Read and validate one definition file."""
    return _engine.parse(path, RULES)


def load_all(directory: Path = SURVEY_DIR) -> dict[str, Survey]:
    """Every definition, keyed by its version name (``finance.v1``).
    Raises ``SurveyError`` on the first invalid file, or when there is no
    business profile survey."""
    return _engine.load_all(directory, RULES)


__all__ = ["AREAS", "PROFILE_KEY", "RULES", "SURVEY_DIR", "Question", "Section", "Survey",
           "SurveyError", "latest", "load_all", "parse"]
