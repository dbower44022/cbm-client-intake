#!/usr/bin/env python3
"""Build a chapter's information page from the deployment guide's stage 8.

    uv run python scripts/chapter_form/build_page.py --chapter "Boston Business Mentors" --out PATH

Writes one self-contained HTML page (no network, no store) holding every question
in stage 8's ``fields`` lists, each with what it means, where to find the answer
and what goes wrong if it is wrong, plus the answer checks from ``fields.CHECKS``.
Publish it as a claude.ai artifact and share it by link (deployment guide
step 8.1).

Answers are kept in the viewer's own browser. The page never saves anywhere
else, because a page that uses the shared store cannot be opened for editing by
anyone outside the publisher's organization (verified in the platform's contract,
09-23-26). The "Copy all answers" button produces one block of text; the person
emails it, "Load answers" merges a block in, and ``to_values.py`` writes the
values file from the final block (step 8.10).
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fields as form  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent / "page_template.html"


def page_data(chapter: str) -> dict:
    stage = form.load_stage()
    secrets_step = next(s for s in stage["steps"] if s["id"] == "8.7")
    secret_lines = []
    for a in secrets_step["actions"]:
        secret_lines.extend(a.get("items") or [])
    return {
        "chapter": chapter,
        "storageKey": "chapter-form:" + "".join(c for c in chapter.lower() if c.isalnum()),
        "header": form.BLOCK_HEADER,
        "checks": {k: {"pattern": p, "message": m} for k, (p, m) in form.CHECKS.items()},
        "sections": form.sections(stage),
        "secrets": secret_lines,
        "webinarSecret": form.WEBINAR_SECRET,
        "guideVersion": stage.get("version"),
        "neededBy": form.NEEDED_BY,
    }


def build(chapter: str, title: str) -> str:
    data = json.dumps(page_data(chapter), ensure_ascii=False).replace("</", "<\\/")
    text = TEMPLATE.read_text()
    return (text.replace("{{TITLE}}", html.escape(title))
                .replace("{{CHAPTER}}", html.escape(chapter))
                .replace("{{DATA}}", data))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chapter", required=True, help="the chapter's full name, as on the form")
    ap.add_argument("--title", help="the page's short name; default: the first word + Chapter Information")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv[1:])
    title = args.title or f"{args.chapter.split()[0]} Chapter Information"
    Path(args.out).write_text(build(args.chapter, title))
    print(f"wrote {args.out} ({len(form.all_fields())} questions)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
