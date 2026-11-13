"""Business Evaluation survey definitions (evaluation/surveys.py, ruling BE9).

Every shipped definition must load; an invalid one fails here, before a
deploy, rather than on a client's screen."""
from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import surveys
from evaluation.surveys import SurveyError

SURVEY_DIR = surveys.SURVEY_DIR


def test_every_shipped_definition_loads():
    loaded = surveys.load_all()
    assert {"business-profile.v1", "finance.v1", "marketing.v1"} <= set(loaded)
    assert loaded["finance.v1"].area == "Finance"
    assert loaded["marketing.v1"].area == "Marketing"
    assert loaded["business-profile.v1"].area == ""
    assert surveys.latest(loaded, "finance").ref == "finance.v1"
    assert surveys.latest(loaded, "nope") is None


@pytest.mark.parametrize("ref", ["business-profile.v1", "finance.v1", "marketing.v1"])
def test_the_pilot_surveys_stay_short(ref):
    # Phase 1 prompt: 12 to 18 questions each, under 15 minutes.
    survey = surveys.load_all()[ref]
    assert 12 <= len(survey.questions) <= 18


@pytest.mark.parametrize("path", sorted(SURVEY_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_every_question_says_what_the_analysis_needs_it_for(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(lines):
        if line.lstrip().startswith("- id:"):
            assert lines[n - 1].strip().startswith("# For:"), \
                f"{path.name} line {n + 1}: a question without its '# For:' comment"


GOOD = """\
key: finance
version: 1
area: Finance
title: Finance
introduction: Hello.
sections:
  - title: One
    questions:
      - id: a
        label: A?
        type: yes_no
"""

PROFILE = """\
key: business-profile
version: 1
title: About
introduction: Hello.
sections:
  - title: One
    questions:
      - id: a
        label: A?
        type: short_text
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_minimal_definition_parses(tmp_path):
    survey = surveys.parse(_write(tmp_path, "finance.v1.yaml", GOOD))
    assert survey.ref == "finance.v1"
    assert survey.questions["a"].type == "yes_no"


@pytest.mark.parametrize("name,text,fault", [
    ("finance.yaml", GOOD, "file name"),
    ("finance.v2.yaml", GOOD, "version"),
    ("marketing.v1.yaml", GOOD, "key"),
    ("finance.v1.yaml", GOOD.replace("area: Finance", "area: Money"), "area"),
    ("finance.v1.yaml", GOOD.replace("title: Finance\n", ""), "'title' is missing"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: slider"), "type"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: single_choice"), "two text options"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: yes_no\n        options: [a, b]"),
     "only a choice question"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: yes_no\n        required: maybe"),
     "true or false"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: yes_no\n        low: x"), "scale"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no", "type: yes_no\n        max: 1"), "'max'"),
    ("finance.v1.yaml", GOOD.replace("type: yes_no",
                                     "type: multiple_choice\n        options: [a, b]\n        max: 2"),
     "'max'"),
    ("finance.v1.yaml", GOOD.replace("id: a", "id: Bad-Id"), "id"),
    ("finance.v1.yaml", GOOD + "      - id: a\n        label: Again?\n        type: yes_no\n",
     "used twice"),
    ("finance.v1.yaml", GOOD + "colour: blue\n", "unknown key"),
    ("finance.v1.yaml", "key: [", "not valid YAML"),
    # YAML reads a bare Yes or No as true or false: it must be quoted.
    ("finance.v1.yaml", GOOD.replace("type: yes_no",
                                     "type: single_choice\n        options:\n          - Yes\n          - No"),
     "two text options"),
])
def test_an_invalid_definition_is_refused_by_name(tmp_path, name, text, fault):
    with pytest.raises(SurveyError) as err:
        surveys.parse(_write(tmp_path, name, text))
    assert fault in str(err.value)
    assert name in str(err.value)


def test_the_business_profile_is_not_an_area(tmp_path):
    with pytest.raises(SurveyError, match="not an evaluation area"):
        surveys.parse(_write(tmp_path, "business-profile.v1.yaml",
                             PROFILE.replace("title: About", "area: Finance\ntitle: About")))


def test_load_all_needs_a_business_profile(tmp_path):
    _write(tmp_path, "finance.v1.yaml", GOOD)
    with pytest.raises(SurveyError, match="no business-profile survey"):
        surveys.load_all(tmp_path)
    _write(tmp_path, "business-profile.v1.yaml", PROFILE)
    assert set(surveys.load_all(tmp_path)) == {"finance.v1", "business-profile.v1"}
