"""Survey definitions: the file format and the loader (ruling BE9, BE23).

One survey per file, ``<key>.v<n>.yaml``, in the folder a survey purpose
names. A file is never edited once someone has answered it: a changed
question is a new version, so every stored answer names the exact questions
it belongs to (``Survey.ref``, such as ``finance.v1``).

The format::

    key: finance                 # matches the file name
    version: 1                   # matches the file name
    title: Finance
    introduction: >-
      One paragraph the person answering reads first.
    sections:
      - title: Money coming in
        intro: Optional text above the questions.
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

A survey purpose may add top-level keys of its own and checks of its own
through ``LoaderRules``: each extra key is read as optional text and passed
to the purpose's ``Survey`` subclass under the same name. ``parse`` and
``load_all`` raise ``SurveyError`` naming the file and the fault.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

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

_FILE = re.compile(r"^(?P<key>[a-z][a-z0-9-]*)\.v(?P<version>[1-9][0-9]*)\.yaml$")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SURVEY_KEYS = {"key", "version", "title", "introduction", "sections"}
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
    max: int = 0          # multiple_choice: the most that may be picked; 0 = any
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
    questions: dict[str, Question] = field(default_factory=dict, compare=False, repr=False)

    @property
    def ref(self) -> str:
        """The version name stored with the answers, such as ``finance.v1``."""
        return f"{self.key}.v{self.version}"


@dataclass(frozen=True)
class LoaderRules:
    """What a survey purpose adds to the format.

    ``extra_keys``: top-level keys its files may carry, each passed to
    ``survey_class`` as a keyword of the same name. ``check(raw, where)``:
    runs after the key, version and extra keys are read, and raises
    ``SurveyError`` with ``where`` at the start of the message.
    ``required_keys``: survey keys ``load_all`` insists on."""

    extra_keys: tuple[str, ...] = ()
    survey_class: type = Survey
    check: Optional[Callable[[dict, str], None]] = None
    required_keys: tuple[str, ...] = ()


PLAIN = LoaderRules()


def text(raw: dict, name: str, where: str, *, required: bool = True) -> str:
    """One text value from a definition, stripped; ``SurveyError`` when it is
    not text, or missing and required."""
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
        id=qid, label=text(raw, "label", where), type=qtype, required=required,
        help=text(raw, "help", where, required=False),
        options=tuple(o.strip() for o in options or ()), max=most,
        low=text(raw, "low", where, required=False),
        high=text(raw, "high", where, required=False),
    )


def parse(path: Path, rules: LoaderRules = PLAIN) -> Survey:
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
    extra = set(raw) - _SURVEY_KEYS - set(rules.extra_keys)
    if extra:
        raise SurveyError(f"{where}: unknown key(s) {sorted(extra)}")
    if raw.get("key") != match["key"]:
        raise SurveyError(f"{where}: key {raw.get('key')!r} does not match the file name")
    if raw.get("version") != int(match["version"]):
        raise SurveyError(f"{where}: version {raw.get('version')!r} does not match the file name")
    extras = {name: text(raw, name, where, required=False) for name in rules.extra_keys}
    if rules.check is not None:
        rules.check({**raw, **extras}, where)
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
        sections.append(Section(title=text(sec, "title", swhere),
                                intro=text(sec, "intro", swhere, required=False),
                                questions=tuple(questions)))
    return rules.survey_class(
        key=raw["key"], version=raw["version"], title=text(raw, "title", where),
        introduction=text(raw, "introduction", where), sections=tuple(sections),
        questions=by_id, **extras)


def load_all(directory: Path, rules: LoaderRules = PLAIN) -> dict[str, Survey]:
    """Every definition in a folder, keyed by its version name (``finance.v1``).
    Raises ``SurveyError`` on the first invalid file, or when a survey the
    rules require is absent."""
    surveys: dict[str, Survey] = {}
    for path in sorted(directory.glob("*.yaml")):
        survey = parse(path, rules)
        surveys[survey.ref] = survey
    for key in rules.required_keys:
        if not any(s.key == key for s in surveys.values()):
            raise SurveyError(f"{directory}: no {key} survey")
    return surveys


def latest(surveys: dict[str, Survey], key: str) -> Optional[Survey]:
    """The highest version of one survey, which is what a new link opens."""
    found = [s for s in surveys.values() if s.key == key]
    return max(found, key=lambda s: s.version) if found else None
