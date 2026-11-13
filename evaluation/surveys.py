"""Survey definitions for the Business Evaluation (plan § 2, ruling BE9).

One survey per file, ``evaluation/surveys/<key>.v<n>.yaml``. A file is never
edited once a client has answered it: a changed question is a new version, so
every Business Evaluation record names the exact questions its answers belong
to (``surveyVersion``, such as ``finance.v1``).

The format::

    key: finance                 # matches the file name
    version: 1                   # matches the file name
    area: Finance                # the CRM's evaluationArea value; absent on
                                 # the business profile, which is not an area
    title: Finance
    introduction: >-
      One paragraph the client reads first.
    sections:
      - title: Money coming in
        questions:
          - id: revenue_last_year          # unique in the survey, snake_case
            label: Roughly how much …?
            help: An estimate is fine.     # optional
            type: currency
            required: true                 # optional, default false
            options: [...]                 # single_choice / multiple_choice only
            max: 3                         # multiple_choice only, optional
            low: Not at all                # scale only, optional
            high: Completely               # scale only, optional

``load_all`` validates every file and raises ``SurveyError`` naming the file and
the fault; ``tests/test_evaluation_surveys.py`` fails on an invalid one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SURVEY_DIR = Path(__file__).resolve().parent / "surveys"

# The business profile is answered once per engagement (ruling BE8).
PROFILE_KEY = "business-profile"

QUESTION_TYPES = (
    "short_text",       # one line
    "long_text",        # a paragraph
    "single_choice",    # one of the options
    "multiple_choice",  # any of the options
    "number",           # a whole or decimal number
    "currency",         # dollars
    "scale",            # 1 to 5
    "yes_no",           # yes or no
)
CHOICE_TYPES = ("single_choice", "multiple_choice")

AREAS = ("Finance", "Competition", "Marketing", "Funding", "Product", "Information Technology")

_FILE = re.compile(r"^(?P<key>[a-z][a-z0-9-]*)\.v(?P<version>[1-9][0-9]*)\.yaml$")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SURVEY_KEYS = {"key", "version", "area", "title", "introduction", "sections"}
_SECTION_KEYS = {"title", "intro", "questions"}
_QUESTION_KEYS = {"id", "label", "help", "type", "required", "options", "max", "low", "high"}


class SurveyError(ValueError):
    """A survey definition that cannot be used. The message names the file."""


@dataclass(frozen=True)
class Question:
    id: str
    label: str
    type: str
    required: bool = False
    help: str = ""
    options: tuple[str, ...] = ()
    max: int = 0          # multiple_choice: the most the client may pick; 0 = any
    low: str = ""
    high: str = ""


@dataclass(frozen=True)
class Section:
    title: str
    questions: tuple[Question, ...]
    intro: str = ""


@dataclass(frozen=True)
class Survey:
    key: str
    version: int
    title: str
    introduction: str
    sections: tuple[Section, ...]
    area: str = ""
    questions: dict[str, Question] = field(default_factory=dict, compare=False, repr=False)

    @property
    def ref(self) -> str:
        """The version name stored on the CRM record, such as ``finance.v1``."""
        return f"{self.key}.v{self.version}"


def _text(raw: dict, name: str, where: str, *, required: bool = True) -> str:
    value = raw.get(name, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise SurveyError(f"{where}: '{name}' must be text")
    if required and not value.strip():
        raise SurveyError(f"{where}: '{name}' is missing")
    return value.strip()


def _question(raw: Any, where: str) -> Question:
    if not isinstance(raw, dict):
        raise SurveyError(f"{where}: a question must be a mapping")
    extra = set(raw) - _QUESTION_KEYS
    if extra:
        raise SurveyError(f"{where}: unknown key(s) {sorted(extra)}")
    qid = raw.get("id")
    if not isinstance(qid, str) or not _ID.match(qid):
        raise SurveyError(f"{where}: id {qid!r} must be lower-case letters, digits and underscores")
    where = f"{where} '{qid}'"
    qtype = raw.get("type")
    if qtype not in QUESTION_TYPES:
        raise SurveyError(f"{where}: type {qtype!r} is not one of {', '.join(QUESTION_TYPES)}")
    required = raw.get("required", False)
    if not isinstance(required, bool):
        raise SurveyError(f"{where}: 'required' must be true or false")
    options = raw.get("options")
    if qtype in CHOICE_TYPES:
        if not isinstance(options, list) or len(options) < 2 \
                or not all(isinstance(o, str) and o.strip() for o in options):
            raise SurveyError(f"{where}: a {qtype} question needs at least two text options")
        if len(set(options)) != len(options):
            raise SurveyError(f"{where}: options repeat")
    elif options is not None:
        raise SurveyError(f"{where}: only a choice question takes options")
    most = raw.get("max", 0)
    if "max" in raw and (qtype != "multiple_choice" or not isinstance(most, int)
                         or isinstance(most, bool) or not 1 <= most < len(options)):
        raise SurveyError(f"{where}: 'max' is for a multiple_choice question, "
                          f"between 1 and one fewer than its options")
    if qtype != "scale" and ("low" in raw or "high" in raw):
        raise SurveyError(f"{where}: only a scale question takes 'low' and 'high'")
    return Question(
        id=qid, label=_text(raw, "label", where), type=qtype, required=required,
        help=_text(raw, "help", where, required=False),
        options=tuple(o.strip() for o in options or ()), max=most,
        low=_text(raw, "low", where, required=False),
        high=_text(raw, "high", where, required=False),
    )


def parse(path: Path) -> Survey:
    """Read and validate one definition file."""
    where = path.name
    match = _FILE.match(path.name)
    if not match:
        raise SurveyError(f"{where}: the file name must be <key>.v<n>.yaml")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SurveyError(f"{where}: not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise SurveyError(f"{where}: the file must hold a mapping")
    extra = set(raw) - _SURVEY_KEYS
    if extra:
        raise SurveyError(f"{where}: unknown key(s) {sorted(extra)}")
    if raw.get("key") != match["key"]:
        raise SurveyError(f"{where}: key {raw.get('key')!r} does not match the file name")
    if raw.get("version") != int(match["version"]):
        raise SurveyError(f"{where}: version {raw.get('version')!r} does not match the file name")
    area = _text(raw, "area", where, required=False)
    if raw["key"] == PROFILE_KEY:
        if area:
            raise SurveyError(f"{where}: the business profile is not an evaluation area")
    elif area not in AREAS:
        raise SurveyError(f"{where}: area {area!r} is not one of {', '.join(AREAS)}")
    sections_raw = raw.get("sections")
    if not isinstance(sections_raw, list) or not sections_raw:
        raise SurveyError(f"{where}: 'sections' must be a non-empty list")
    sections: list[Section] = []
    by_id: dict[str, Question] = {}
    for n, sec in enumerate(sections_raw, 1):
        swhere = f"{where} section {n}"
        if not isinstance(sec, dict):
            raise SurveyError(f"{swhere}: a section must be a mapping")
        extra = set(sec) - _SECTION_KEYS
        if extra:
            raise SurveyError(f"{swhere}: unknown key(s) {sorted(extra)}")
        qs_raw = sec.get("questions")
        if not isinstance(qs_raw, list) or not qs_raw:
            raise SurveyError(f"{swhere}: 'questions' must be a non-empty list")
        questions = []
        for q in qs_raw:
            question = _question(q, swhere)
            if question.id in by_id:
                raise SurveyError(f"{where}: question id '{question.id}' is used twice")
            by_id[question.id] = question
            questions.append(question)
        sections.append(Section(title=_text(sec, "title", swhere),
                                intro=_text(sec, "intro", swhere, required=False),
                                questions=tuple(questions)))
    return Survey(key=raw["key"], version=raw["version"], area=area,
                  title=_text(raw, "title", where),
                  introduction=_text(raw, "introduction", where),
                  sections=tuple(sections), questions=by_id)


def load_all(directory: Path = SURVEY_DIR) -> dict[str, Survey]:
    """Every definition, keyed by its version name (``finance.v1``).
    Raises ``SurveyError`` on the first invalid file, or when there is no
    business profile survey."""
    surveys: dict[str, Survey] = {}
    for path in sorted(directory.glob("*.yaml")):
        survey = parse(path)
        surveys[survey.ref] = survey
    if not any(s.key == PROFILE_KEY for s in surveys.values()):
        raise SurveyError(f"{directory}: no {PROFILE_KEY} survey")
    return surveys


def latest(surveys: dict[str, Survey], key: str) -> Survey | None:
    """The highest version of one survey, which is what a new link sends."""
    found = [s for s in surveys.values() if s.key == key]
    return max(found, key=lambda s: s.version) if found else None
