"""Render the New Chapter Deployment Guide from its step data.

    uv run python scripts/render_deployment_guide.py          # write guide/
    uv run python scripts/render_deployment_guide.py --check  # exit 1 if guide/ is stale or the data is inconsistent

Reads prds/chapter-network/deployment-guide/steps/stage-*.yaml and writes one
Markdown page per stage, plus an index, to .../deployment-guide/guide/. The YAML
is the source; the pages are never edited by hand. Field meanings:
steps/README.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "prds" / "chapter-network" / "deployment-guide"
STEPS = ROOT / "steps"
GUIDE = ROOT / "guide"

WHO = {"chapter": "The chapter", "central": "The central support organization", "both": "The chapter and the central support organization"}
DEFAULT_IF_NOT = "Stop, and ask the central support organization before going on."


def _who(text: str) -> str:
    head, _, rest = (text or "").partition(" ")
    base = WHO.get(head.rstrip(",;:"), None)
    return f"{base}{(' ' + rest) if rest else ''}" if base else text


def _slug(stage: dict) -> str:
    words = "".join(c if c.isalnum() else " " for c in stage["name"].lower()).split()
    return f"{int(stage['stage']):02d}-" + "-".join(words)


def render_stage(stage: dict) -> str:
    out: list[str] = []
    out.append(f"# Stage {stage['stage']} — {stage['name']}\n")
    out.append(f"**Version:** {stage.get('version', '0.1')}  ")
    out.append(f"**Last Updated:** {stage.get('updated', '')}  ")
    out.append(f"**Generated from** `steps/stage-{int(stage['stage']):02d}.yaml` — do not edit this page; edit the YAML and re-render.\n")
    out.append("---\n")
    out.append("## Why this stage\n")
    out.append(stage["why"].strip() + "\n")
    out.append(f"**Who:** {stage['who'].strip()}  ")
    out.append(f"**Time:** {stage.get('time', 'not known yet').strip()}  ")
    out.append(f"**When this stage is done:** {stage['unlocks'].strip()}\n")
    before = stage.get("before_you_start") or []
    out.append("**Before you start:**" + ("\n" if before else " nothing.\n"))
    out.extend(f"- {b.strip()}" for b in before)
    out.append("")
    out.append("**Steps in this stage:**\n")
    out.extend(f"- {s['id']} {s['name']}" for s in stage["steps"])
    out.append("")
    for s in stage["steps"]:
        out.append("---\n")
        out.append(f"## {s['id']} {s['name']}\n")
        out.append(f"**Why:** {s['why'].strip()}\n")
        first = s.get("first") or []
        out.append(f"**Who:** {_who(s['who'].strip())}\n")
        out.append("**Finish first:**" + ("\n" if first else " nothing.\n"))
        if first:
            out.extend(f"- step {f} {NAMES.get(str(f), '')}".rstrip() for f in first)
            out.append("")
        if not str(s.get("status", "")).startswith("done-for-real"):
            out.append("> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.\n")
        out.append("**Do this:**\n")
        for n, a in enumerate(s.get("actions") or [], 1):
            out.append(f"{n}. {a['do'].strip()}")
            for item in a.get("items") or []:
                out.append(f"   - {str(item).strip()}")
            see = a.get("see")
            if isinstance(see, list):
                out.append("   *You should see:*")
                out.extend(f"   - {str(x).strip()}" for x in see)
            elif see:
                out.append(f"   *You should see:* {see.strip()}")
        out.append("")
        fields = s.get("fields") or []
        if fields:
            out.append("**The questions in this step:**\n")
            for f in fields:
                out.extend(render_field(f))
            out.append("")
        dw = s["done_when"]
        if isinstance(dw, list):
            out.append("**Done when all of these are true:**\n")
            out.extend(f"- {str(x).strip()}" for x in dw)
            out.append("")
        else:
            out.append(f"**Done when:** {dw.strip()}\n")
        if s.get("note"):
            out.append(f"**Note:** {str(s['note']).strip()}\n")
        check = s.get("check") or {}
        if check.get("how"):
            out.append(f"**How to check:** {check['how'].strip()}\n")
        out.append(f"**If it didn't work:** {(s.get('if_not') or DEFAULT_IF_NOT).strip()}\n")
        gw = (s.get("goes_wrong") or "").strip()
        if gw and gw.lower() not in {"nothing known yet.", "nothing known yet", "nothing known."}:
            out.append(f"**What usually goes wrong:** {gw}\n")
    out.append("---\n")
    out.append("## Change log\n")
    out.append("| Version | Date | Change |\n|---|---|---|")
    for c in stage.get("changes") or []:
        out.append(f"| {c['version']} | {c['date']} | {c['change'].strip()} |")
    out.append("")
    return "\n".join(out)


BY = {"chapter": "the chapter", "central": "the central support organization"}


def render_field(f: dict) -> list[str]:
    """One question of the chapter information form, as the guide prints it.
    The same entry drives the web page (scripts/chapter_form/build_page.py)."""
    flags = [f"answered by {BY.get(f['by'], f['by'])}"]
    flags.append("required" if f.get("required") else "may be marked not known yet")
    if f.get("later"):
        flags.append(f"filled in at step {f['later']}")
    if f.get("show_if"):
        flags.append("asked only for a chapter that runs Zoom webinars")
    lines = [f"- **{f['label']}** (`{f['key']}`) — {'; '.join(flags)}."]
    lines.append(f"  - *What it is:* {f['meaning'].strip()}")
    lines.append(f"  - *Where to find it:* {f['source'].strip()}")
    lines.append(f"  - *If it is wrong:* {f['wrong'].strip()}")
    if "default" in f:
        d = f["default"]
        shown = ("yes" if d else "no") if isinstance(d, bool) else d
        lines.append(f"  - *Recommended:* {shown}")
    elif f.get("example"):
        lines.append(f"  - *Example:* {f['example']}")
    return lines


def render_index(stages: list[dict]) -> str:
    out = ["# New Chapter Deployment Guide\n",
           "**Generated from** `steps/` — do not edit this page; edit the YAML and re-render.\n",
           "The guide takes a new chapter from nothing to a running system. Work through the stages in order. "
           "Each stage opens with why it exists, who does it, and what must be finished first.\n",
           "---\n"]
    for st in stages:
        out.append(f"{st['stage']}. [{st['name']}]({_slug(st)}.md)")
        out.append(f"   {st['why'].strip().split('. ')[0].rstrip('.')}.")
    out.append("")
    return "\n".join(out)


def load() -> list[dict]:
    stages = [yaml.safe_load(p.read_text()) for p in sorted(STEPS.glob("stage-*.yaml"))]
    return sorted(stages, key=lambda s: int(s["stage"]))


def information_check(stages: list[dict]) -> list[str]:
    """The plan's information check, run on the data: every value is produced by
    exactly one step and needed by at least one, and every `first` names a step."""
    produced: dict[str, list[str]] = {}
    needed: dict[str, list[str]] = {}
    ids = {s["id"] for st in stages for s in st["steps"]}
    problems = []
    for st in stages:
        for s in st["steps"]:
            for v in s.get("produces") or []:
                produced.setdefault(v, []).append(s["id"])
            for v in s.get("needs") or []:
                needed.setdefault(v, []).append(s["id"])
            for f in s.get("first") or []:
                if str(f) not in ids:
                    problems.append(f"step {s['id']}: 'first' names unknown step {f}")
    for v, where in sorted(produced.items()):
        if len(where) > 1:
            problems.append(f"'{v}' is produced by more than one step: {', '.join(where)}")
        if v not in needed:
            problems.append(f"'{v}' is produced by step {where[0]} but no step needs it")
    for v, where in sorted(needed.items()):
        if v not in produced:
            problems.append(f"'{v}' is needed by step {', '.join(where)} but no step produces it")
            continue
        # order: a value must exist before the first step that uses it
        src = produced[v][0]
        for use in where:
            if _pos(use) <= _pos(src):
                problems.append(f"'{v}' is needed by step {use} but only produced later, by step {src}")
    return problems


def _pos(step_id: str) -> tuple[int, int]:
    stage, _, n = step_id.partition(".")
    return int(stage), int(n)


NAMES: dict[str, str] = {}


def build(stages: list[dict] | None = None) -> dict[Path, str]:
    stages = stages if stages is not None else load()
    NAMES.update({s["id"]: s["name"] for st in stages for s in st["steps"]})
    files = {GUIDE / f"{_slug(st)}.md": render_stage(st) for st in stages}
    files[GUIDE / "README.md"] = render_index(stages)
    return files


def main() -> int:
    stages = load()
    problems = information_check(stages)
    for line in problems:
        print(f"information check: {line}")
    files = build(stages)
    if "--check" in sys.argv:
        stale = [p for p, text in files.items() if not p.exists() or p.read_text() != text]
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)}")
        return 1 if stale or problems else 0
    GUIDE.mkdir(exist_ok=True)
    for p, text in files.items():
        p.write_text(text)
    print(f"rendered {len(files)} pages to {GUIDE.relative_to(ROOT.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
