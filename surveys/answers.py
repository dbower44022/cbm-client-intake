"""Answers: checking a value against its question, the required answers, the
state a survey is in, and the two forms the answers are handed on in — the
question-and-answer text for people, and version-stamped JSON for machines.
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Optional

from .definitions import Question, Survey

# What the page shows for a survey.
NOT_STARTED, IN_PROGRESS, SUBMITTED = "not_started", "in_progress", "submitted"

SHORT_MAX = 500
LONG_MAX = 5000
NUMBER_MAX = 1e12


def state_of(row: Optional[dict[str, Any]]) -> str:
    if not row:
        return NOT_STARTED
    if row.get("submitted_at"):
        return SUBMITTED
    return IN_PROGRESS if row.get("answers") else NOT_STARTED


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number) or abs(number) > NUMBER_MAX:
        return None
    return int(number) if number.is_integer() else number


def check_value(q: Question, value: Any) -> tuple[Any, Optional[str]]:
    """A value in its stored form, or the reason it cannot be accepted."""
    if q.type in ("short_text", "long_text"):
        if not isinstance(value, str):
            return None, "Please type an answer."
        limit = SHORT_MAX if q.type == "short_text" else LONG_MAX
        text = value.strip()
        if len(text) > limit:
            return None, f"Please keep this under {limit} characters."
        return text, None
    if q.type == "single_choice":
        if value not in q.options:
            return None, "Please choose one of the answers."
        return value, None
    if q.type == "multiple_choice":
        if not isinstance(value, list) or not all(v in q.options for v in value):
            return None, "Please choose from the answers."
        picked = [o for o in q.options if o in value]
        if q.max and len(picked) > q.max:
            return None, f"Please choose no more than {q.max}."
        return picked, None
    if q.type == "yes_no":
        if value not in ("Yes", "No"):
            return None, "Please choose yes or no."
        return value, None
    if q.type == "scale":
        number = _number(value)
        if number is None or number not in (1, 2, 3, 4, 5):
            return None, "Please choose a number from 1 to 5."
        return int(number), None
    number = _number(value)
    if number is None:
        return None, "Please enter a number."
    if q.type == "currency" and number < 0:
        return None, "Please enter an amount of zero or more."
    return number, None


def clean_answers(survey: Survey, raw: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """The answers this survey can store, and a message per question whose
    value cannot be. Unknown question ids are dropped; blanks are left out."""
    if not isinstance(raw, dict):
        return {}, {}
    kept: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for qid, value in raw.items():
        question = survey.questions.get(qid)
        if question is None or _blank(value):
            continue
        stored, error = check_value(question, value)
        if error:
            errors[qid] = error
        elif not _blank(stored):
            kept[qid] = stored
    return kept, errors


def missing_required(survey: Survey, answers: dict[str, Any]) -> dict[str, str]:
    return {q.id: "This question needs an answer." for q in survey.questions.values()
            if q.required and _blank(answers.get(q.id))}


def _shown(q: Question, value: Any) -> str:
    if _blank(value):
        return "Not answered"
    if isinstance(value, list):
        return "; ".join(value)
    if q.type == "currency":
        return f"${value:,}" if isinstance(value, int) else f"${value:,.2f}"
    if q.type == "scale":
        ends = f" ({q.low} to {q.high})" if q.low and q.high else ""
        return f"{value} out of 5{ends}"
    return str(value)


def readable_html(survey: Survey, answers: dict[str, Any]) -> str:
    """The answers as question-and-answer text for the people who read them."""
    parts = [f"<p><em>{html.escape(survey.title)} survey, version {survey.version}</em></p>"]
    for section in survey.sections:
        parts.append(f"<h3>{html.escape(section.title)}</h3>")
        for q in section.questions:
            shown = html.escape(_shown(q, answers.get(q.id))).replace("\n", "<br>")
            parts.append(f"<p><strong>{html.escape(q.label)}</strong><br>{shown}</p>")
    return "\n".join(parts)


def answers_json(survey: Survey, answers: dict[str, Any]) -> str:
    """The answers as JSON: version-stamped, in question order."""
    ordered = {q.id: answers[q.id] for s in survey.sections for q in s.questions if q.id in answers}
    return json.dumps({"survey": survey.ref, "answers": ordered}, ensure_ascii=False)
