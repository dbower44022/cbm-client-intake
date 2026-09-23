#!/usr/bin/env python3
"""Write a chapter's values file from the answers its chapter information page copied.

    uv run python scripts/chapter_form/to_values.py ANSWERS-FILE            # check, then write
    uv run python scripts/chapter_form/to_values.py ANSWERS-FILE --check    # check only

ANSWERS-FILE holds the block the page's "Copy all answers" button produces: a
first line reading CHAPTER-INFORMATION-ANSWERS v1, then JSON. The file is written
to prds/chapter-network/chapters/<slug>-values.yaml, the place ruled on 09-19-26
(deployment guide step 8.10).

Checks, in order, each naming the question by its label as the page shows it:
every answer against its question's rule (fields.problem); then the settings
generator's own refusals, by rendering a trial spec with made-up secrets. A
refusal about the shared drive identifier is reported as owed at step 10.5, not
as a failure, because that answer does not exist until then.

Exit 0 when the file was written (or would be, with --check); 1 when any answer
must change first; 2 when the block cannot be read.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fields as form  # noqa: E402

CHAPTERS = form.ROOT / "prds" / "chapter-network" / "chapters"
# A switch marked not known yet. Written as this word, never as false, so the
# file cannot pass an unanswered switch off as a decision; the settings
# generator (scripts/rehearsal/render_spec.py) refuses it at step 11.2.
OWED = "owed"
SECRET_MARKERS = ("-----BEGIN", "private_key", "PRIVATE KEY")


def read_block(text: str) -> dict:
    text = text.strip()
    head, _, body = text.partition("\n")
    if head.strip() != form.BLOCK_HEADER:
        raise ValueError(f"the first line must read {form.BLOCK_HEADER!r}; it reads {head.strip()[:60]!r}")
    data = json.loads(body)
    if not isinstance(data.get("answers"), dict):
        raise ValueError("the block holds no answers")
    return data


def answer_problems(answers: dict, stage: dict | None = None) -> list[str]:
    out = []
    for f in form.all_fields(stage):
        if not form.is_shown(f, answers):
            continue
        why = form.problem(f, answers.get(f["key"]))
        if why:
            out.append(f"{f['label']} ({f['key']}): {why}")
        value = str((answers.get(f["key"]) or {}).get("value") or "")
        if any(m in value for m in SECRET_MARKERS):
            out.append(f"{f['label']} ({f['key']}): this looks like a secret. Secrets never go on the form.")
    return out


def owed_answers(answers: dict, stage: dict | None = None) -> list[str]:
    """Required answers marked not known yet, each with the step that needs it."""
    return [f"{f['label']} ({f['key']}): marked not known yet; needed by {form.needed_by(f)}."
            for f in form.all_fields(stage)
            if form.is_shown(f, answers) and form.owed(f, answers.get(f["key"]))]


def build_values(answers: dict, stage: dict | None = None) -> dict:
    values: dict = {"chapter": {}, "web": {}, "google": {}, "zoom": {}, "crm": {}, "secrets": [], "flags": {}}
    for f in form.all_fields(stage):
        section, _, name = f["key"].partition(".")
        a = answers.get(f["key"]) or {}
        shown = form.is_shown(f, answers)
        value = a.get("value") if shown and not a.get("notYet") else None
        if f["kind"] == "bool":
            if shown and a.get("notYet"):
                values[section][name] = OWED
            else:
                values[section][name] = bool(value) if value is not None else False
        else:
            values[section][name] = "" if value is None else str(value).strip()
    # Not asked: empty means the applications' own events page (step 8.3's note).
    values["web"]["events_public_base_url"] = ""
    values["secrets"] = list(form.SECRETS) + ([form.WEBINAR_SECRET] if values["flags"].get("zoom_events") else [])
    return values


def _render_spec():
    path = form.ROOT / "scripts" / "rehearsal" / "render_spec.py"
    spec = importlib.util.spec_from_file_location("render_spec_for_form", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def generator_problems(values: dict) -> tuple[list[str], list[str]]:
    """(problems, owed): the settings generator's refusals on a trial render."""
    rs = _render_spec()
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "key.json"
        key.write_text(json.dumps({"type": "service_account", "private_key": "trial"}))
        from cryptography.fernet import Fernet
        secrets = {"ESPO_API_KEY": "t", "ESPO_PROVISION_USERNAME": "t", "ESPO_PROVISION_PASSWORD": "t",
                   "SESSION_SECRET": "t", "APP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                   "GOOGLE_SERVICE_ACCOUNT_KEY_FILE": str(key)}
        trial = json.loads(json.dumps(values))
        trial["flags"] = {k: (False if v == OWED else v) for k, v in trial["flags"].items()}
        for section in ("web", "google", "zoom", "crm"):  # answers owed later must not fail the trial
            for k, v in trial.get(section, {}).items():
                if v == "" and k.endswith("_url"):
                    trial[section][k] = "https://owed.invalid/"
        try:
            rs.build_spec(trial, secrets)
        except (ValueError, KeyError) as exc:
            msg = str(exc)
            if "shared_drive_id" in msg:
                return [], ["Shared drive identifier (google.shared_drive_id): owed at step 10.5, before step 11.2."]
            return [f"The settings generator refuses these answers: {msg}"], []
    return [], []


def header(data: dict, now: dt.datetime) -> str:
    lines = [
        "# Chapter information form — WRITTEN FROM THE CHAPTER INFORMATION PAGE. Do not edit by hand:",
        "# change the answer on the page and write this file again (deployment guide step 8.10).",
        f"# written: {now.strftime('%m-%d-%y %H:%M')}",
    ]
    signoffs = data.get("signoffs") or []
    owed_now = owed_answers(data.get("answers") or {})
    if owed_now:
        lines.append("# OWED — answers marked not known yet, each with the step that needs it:")
        lines.extend(f"#   {o}" for o in owed_now)
    if signoffs:
        lines.append("# reviewed by: " + " and ".join(s.get("name", "?") for s in signoffs))
        lines.append("# reviewed on: " + ", ".join(sorted({s.get("date", "?") for s in signoffs})))
    else:
        lines.append("# reviewed by: NOT YET SIGNED OFF (step 8.9)")
    lines.append("# No secret values: the secrets section lists names only.")
    return "\n".join(lines) + "\n"


COLOUR_TOKENS = [("colour_primary", "--cbm-navy"), ("colour_button", "--cbm-gold"),
                 ("colour_button_hover", "--cbm-btn-bg-hover"), ("colour_text", "--cbm-text")]


def tokens_css(values: dict) -> str | None:
    """The chapter's colour file (deployment guide step 6.5), or None when no
    colour is known. Only --cbm- names on :root, as CHAPTER_TOKENS_URL allows;
    a colour left out keeps Cleveland's value."""
    web = values.get("web") or {}
    lines = [f"  {name}: {web[key]};" for key, name in COLOUR_TOKENS if web.get(key)]
    if not lines:
        return None
    return ("/* Colour file for " + values["chapter"].get("name", "") + ", written from its chapter\n"
            "   information page (deployment guide steps 6.5 and 8.10). Publish it and enter\n"
            "   its address as the colour file's web address. */\n:root {\n" + "\n".join(lines) + "\n}\n")


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(form.ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        data = read_block(Path(args[0]).read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read the answers: {exc}", file=sys.stderr)
        return 2
    answers = data["answers"]
    problems = answer_problems(answers)
    owed = owed_answers(answers)
    values = build_values(answers)
    if not values["chapter"].get("slug"):
        problems.append("Short label (chapter.slug): must be known to write the file, because it names the file.")
    if not problems:
        more, later = generator_problems(values)
        problems += more
        owed += later
    for p in problems:
        print(f"change on the page: {p}")
    for o in owed:
        print(f"owed later: {o}")
    if problems:
        return 1
    out = CHAPTERS / f"{values['chapter']['slug']}-values.yaml"
    if "--check" in argv:
        print(f"check passed; would write {_shown(out)}")
        return 0
    CHAPTERS.mkdir(parents=True, exist_ok=True)
    out.write_text(header(data, dt.datetime.now()) + yaml.safe_dump(values, sort_keys=False, allow_unicode=True))
    print(f"check passed; wrote {_shown(out)}")
    css = tokens_css(values)
    if css:
        tok = CHAPTERS / f"{values['chapter']['slug']}-chapter-tokens.css"
        tok.write_text(css)
        print(f"wrote {_shown(tok)} — publish it for the colour file's web address (step 6.5)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
