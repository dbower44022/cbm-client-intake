"""Turn a training course's Markdown into a step-by-step page (Doug's choice A,
11-21-26): a tick box per step, a progress count, a copy button on every value
and a Reset button, in the look of the live-check runbook pages. The Markdown
stays the one source; rebuild the page after every edit and publish it again.

    uv run python scripts/build_runbook.py training/evaluation-staff-course/evaluation-demo.md
    uv run python scripts/build_runbook.py <course.md> --out <page.html> --title "Short Name"

The reader is ``courses/render.py`` (prds/training-app-plan.md, decision 4),
the same one the application's course page uses; its docstring describes the
Markdown's shape. On this page ``{{training_url}}`` becomes ``--training-url``
and each ``{{signin:<role>}}`` the role's name, never a sign-in: the page is
public.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from courses.render import page_sub, parse, render  # noqa: E402

#: The training system today, the Business Mentors Association's (TR7).
DEFAULT_TRAINING_URL = "https://apps.businessmentorsassociation.org"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--title", default="", help="the page's short name (browser tab, gallery)")
    ap.add_argument("--training-url", default=DEFAULT_TRAINING_URL,
                    help="the training system's address, for {{training_url}}")
    args = ap.parse_args()
    doc = parse(args.source.read_text(encoding="utf-8"))
    out = args.out or args.source.with_suffix(".html")
    out.write_text(render(doc, "runbook:" + args.source.stem, args.title,
                          page_sub(args.training_url)), encoding="utf-8")
    steps = sum(len(s["steps"]) for s in doc["sections"])
    print(f"Wrote {out}: {steps} steps, {len(doc['sections'])} sections.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
