"""Sync the static form dropdown lists to the live EspoCRM enums.

The public intake wizards ship hand-curated value lists in
``forms/<form>/frontend/options.js`` (static so the forms stay fast and need no
CRM call at page load). The CRM-backed lists among them must match the live enum
options verbatim — a value outside the enum 400s the record create. This script
keeps them aligned: it reads the live options from EspoCRM and rewrites only the
arrays wrapped in ``crm-enum`` marker comments, leaving the presentational lists
(how-did-you-hear, phone type, …) and all surrounding comments untouched.

A managed block looks like::

    // >>> crm-enum key=industryExperience field=CMentorProfile.industrySector — generated; ...
    industryExperience: [
      "Accounting and bookkeeping",
      ...
    ],
    // <<< crm-enum

The start marker declares the JS key, the source ``Entity.field``, and an
optional ``exclude="A|B"`` of CRM values the form deliberately omits.

Usage (reads ESPO_BASE_URL / ESPO_API_KEY from the environment / .env)::

    uv run python scripts/sync_form_options.py            # dry-run: print the diff
    uv run python scripts/sync_form_options.py --write     # apply the changes

Dry-run exits non-zero when anything would change, so it doubles as a CI drift
check. ``--write`` applies the changes; review the git diff and commit as usual.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Run from the repo root so the package imports resolve.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient  # noqa: E402

OPTIONS_GLOB = "forms/*/frontend/options.js"

# A managed block: the start marker (capturing key / entity.field / the rest of
# the line, which may carry exclude="…"), the array body, then the end marker.
BLOCK_RE = re.compile(
    r"(?P<start>^(?P<indent>[ \t]*)//[ ]>>> crm-enum"
    r" key=(?P<key>\w+) field=(?P<entity>\w+)\.(?P<field>\w+)(?P<rest>[^\n]*)\n)"
    r"(?P<body>.*?)"
    r"(?P<end>^[ \t]*//[ ]<<< crm-enum[^\n]*$)",
    re.MULTILINE | re.DOTALL,
)
EXCLUDE_RE = re.compile(r'exclude="([^"]*)"')


@dataclass
class Block:
    file: Path
    key: str
    entity: str
    field: str
    exclude: list[str]
    indent: str
    span: tuple[int, int]  # char span of the body to replace
    current: list[str]


def _js_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_body(indent: str, key: str, values: list[str]) -> str:
    """Render the canonical ``key: [ ... ],`` body (one value per line)."""
    inner = indent + "  "
    lines = [f"{indent}{key}: ["]
    lines += [f'{inner}"{_js_escape(v)}",' for v in values]
    lines.append(f"{indent}],")
    return "\n".join(lines) + "\n"


def _parse_current(body: str) -> list[str]:
    """Pull the existing quoted values out of a block body (for diff reporting)."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', body)


def discover_blocks() -> list[Block]:
    blocks: list[Block] = []
    for path in sorted(ROOT.glob(OPTIONS_GLOB)):
        text = path.read_text()
        for m in BLOCK_RE.finditer(text):
            excl = EXCLUDE_RE.search(m.group("rest"))
            blocks.append(
                Block(
                    file=path,
                    key=m.group("key"),
                    entity=m.group("entity"),
                    field=m.group("field"),
                    exclude=excl.group(1).split("|") if excl else [],
                    indent=m.group("indent"),
                    span=(m.start("body"), m.end("body")),
                    current=_parse_current(m.group("body")),
                )
            )
    return blocks


async def fetch_options(client: EspoClient, blocks: list[Block]) -> dict[tuple[str, str], list[str]]:
    """Fetch each distinct (entity, field) enum's live options once."""
    wanted = sorted({(b.entity, b.field) for b in blocks})
    out: dict[tuple[str, str], list[str]] = {}
    for entity, field in wanted:
        opts = await client.metadata_enum_options(entity, field)
        if opts is None:
            raise SystemExit(
                f"ERROR: {entity}.{field} returned no enum options "
                f"(field missing or not an enum?) — aborting without changes."
            )
        out[(entity, field)] = opts
    return out


def _subsector_keys(text: str) -> list[str]:
    """Top-level quoted keys of a client-intake industrySubsector object, if any."""
    m = re.search(r"industrySubsector:\s*\{(.*?)\n\s*\},", text, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"([^"]+)":\s*\[', m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="apply changes (default: dry-run)")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.espo_api_key:
        raise SystemExit("ERROR: ESPO_API_KEY is not set (check .env).")
    print(f"CRM: {settings.espo_base_url}")
    client = EspoClient(settings.espo_base_url, settings.espo_api_key)

    blocks = discover_blocks()
    print(f"Found {len(blocks)} managed list(s) across "
          f"{len({b.file for b in blocks})} file(s).\n")

    live = asyncio.run(fetch_options(client, blocks))

    # Group blocks by file and rebuild each file once (blocks edit disjoint spans).
    changed_files: dict[Path, str] = {}
    drift = False
    for path in sorted({b.file for b in blocks}):
        original = path.read_text()
        file_blocks = [b for b in blocks if b.file == path]
        # Apply replacements back-to-front so earlier spans stay valid.
        new_text = original
        for b in sorted(file_blocks, key=lambda b: b.span[0], reverse=True):
            # Drop blank/whitespace-only enum options (CRM data-hygiene junk —
            # never a valid dropdown choice) and any value the form excludes.
            target = [
                v for v in live[(b.entity, b.field)]
                if v.strip() and v not in b.exclude
            ]
            new_text = (
                new_text[: b.span[0]]
                + _render_body(b.indent, b.key, target)
                + new_text[b.span[1] :]
            )
            added = [v for v in target if v not in b.current]
            removed = [v for v in b.current if v not in target]
            if added or removed:
                drift = True
                print(f"  {path.relative_to(ROOT)}  [{b.key} ← {b.entity}.{b.field}]")
                for v in removed:
                    print(f"      - {v}")
                for v in added:
                    print(f"      + {v}")
                if b.exclude:
                    print(f"      (excluded from form: {', '.join(b.exclude)})")

        # Warn if syncing industrySector orphans an industrySubsector key.
        if "industrySubsector" in new_text:
            sectors = set(
                v
                for b in file_blocks
                if b.key == "industrySector"
                for v in live[(b.entity, b.field)]
            )
            if sectors:
                orphans = [k for k in _subsector_keys(new_text) if k not in sectors]
                if orphans:
                    print(f"  ⚠  {path.relative_to(ROOT)}: industrySubsector keys no "
                          f"longer in industrySector — reconcile manually: {orphans}")

        if new_text != original:
            changed_files[path] = new_text

    if not changed_files:
        print("✓ All managed lists already match the live CRM enums.")
        return 0

    if args.write:
        for path, text in changed_files.items():
            path.write_text(text)
        print(f"\n✓ Wrote {len(changed_files)} file(s). Review the git diff and commit.")
        return 0

    print("\n--- unified diff (dry-run; re-run with --write to apply) ---")
    for path, text in changed_files.items():
        rel = str(path.relative_to(ROOT))
        diff = difflib.unified_diff(
            path.read_text().splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        sys.stdout.writelines(diff)
    print(f"\n{len(changed_files)} file(s) would change. Re-run with --write to apply.")
    return 1 if drift or changed_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
