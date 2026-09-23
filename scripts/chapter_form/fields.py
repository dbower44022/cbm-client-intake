"""The chapter information form's questions, read from the deployment guide.

The questions live in ONE place: the ``fields`` lists in
``prds/chapter-network/deployment-guide/steps/stage-08.yaml``. The readable guide
(``scripts/render_deployment_guide.py``), the web page (``build_page.py``) and the
values-file writer (``to_values.py``) all read them from here, so the three can
never disagree about what is asked or how an answer is checked.

The answer checks are regular expressions held here and embedded into the page,
so the page and the writer apply the same rule.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STAGE_8 = ROOT / "prds" / "chapter-network" / "deployment-guide" / "steps" / "stage-08.yaml"

# One rule per kind of answer: (pattern, the message shown when it fails).
# JavaScript and Python read these patterns identically; keep them to the
# common subset (no look-behind, no named groups).
CHECKS: dict[str, tuple[str, str]] = {
    # At most 25: the label becomes "<label>-intake" (a hosting platform app name,
    # 32 at most) and "<label>-apps" (a Google Cloud project, 30 at most), and
    # both accept only lower case, digits and hyphens, never ending in a hyphen.
    "slug": (r"^[a-z]([a-z0-9-]{0,23}[a-z0-9])?$",
             "Lower-case letters, digits and hyphens only, starting with a letter, not ending with a hyphen, at most 25 characters."),
    "abbreviation": (r"^[A-Za-z0-9&]{2,8}$",
                     "Two to eight letters or digits, no spaces, such as LBM."),
    "url": (r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(:[0-9]+)?(/[^\s]*)?$",
            "A full address beginning with https://, copied from the browser's address bar."),
    "email": (r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$",
              "An email address, such as info@example.org."),
    "domain": (r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$",
               "A domain only, such as example.org: no https://, no @, no spaces, lower case."),
    "text": (r"\S", "This cannot be blank."),
}

# The secret names every chapter has (deployment guide step 8.7), and the one a
# webinar chapter adds. Names only; a value never appears on the form.
SECRETS = [
    "ESPO_API_KEY",
    "ESPO_PROVISION_USERNAME",
    "ESPO_PROVISION_PASSWORD",
    "DATABASE_URL",
    "SESSION_SECRET",
    "APP_ENCRYPTION_KEY",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
]
WEBINAR_SECRET = "ZOOM_CLIENT_SECRET"

BLOCK_HEADER = "CHAPTER-INFORMATION-ANSWERS v1"


def load_stage() -> dict:
    return yaml.safe_load(STAGE_8.read_text())


def sections(stage: dict | None = None) -> list[dict]:
    """The steps that ask questions, in order: {id, name, fields}."""
    stage = stage or load_stage()
    return [{"id": s["id"], "name": s["name"], "fields": s["fields"]}
            for s in stage["steps"] if s.get("fields")]


def all_fields(stage: dict | None = None) -> list[dict]:
    return [f for sec in sections(stage) for f in sec["fields"]]


def is_shown(field: dict, answers: dict) -> bool:
    """A field with ``show_if`` is asked only when that switch is answered yes."""
    cond = field.get("show_if")
    if not cond:
        return True
    a = answers.get(cond) or {}
    return a.get("value") is True


# When a question marked not known yet must be answered, by the part of the
# form it belongs to. A field's own ``needed_by`` overrides this.
NEEDED_BY = {
    "chapter": "step 9.10, where the CRM is set up",
    "crm": "step 9.10, where the CRM is set up",
    "web": "step 11.2, where the applications' settings are generated",
    "google": "step 11.2, where the applications' settings are generated",
    "zoom": "step 11.2, where the applications' settings are generated",
    "flags": "step 11.2, where the applications' settings are generated",
}


def needed_by(field: dict) -> str:
    return field.get("needed_by") or NEEDED_BY[field["key"].partition(".")[0]]


def owed(field: dict, answer: dict | None) -> bool:
    """A required answer marked not known yet: allowed on the form, owed later."""
    return bool((answer or {}).get("notYet")) and bool(field.get("required")) and not field.get("later")


def problem(field: dict, answer: dict | None) -> str | None:
    """Why this answer cannot be used, in plain words, or None when it can.
    "Not known yet" is always an allowed answer (Doug, 09-23-26); a required
    one is reported as owed by ``owed``/``needed_by`` rather than here."""
    answer = answer or {}
    value = answer.get("value")
    if answer.get("notYet"):
        return None
    if value is None or value == "":
        if field.get("later"):
            return None
        return "Not answered yet. Answer it, or mark it not known yet."
    kind = field["kind"]
    if kind == "bool":
        return None if isinstance(value, bool) else "Answer yes or no."
    if kind == "choice":
        return None if value in field.get("options", []) else "Choose one of the listed answers."
    pattern, message = CHECKS[kind]
    return None if re.search(pattern, str(value)) else message
