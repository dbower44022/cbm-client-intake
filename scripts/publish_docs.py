"""Publish repo markdown to the BookStack docs site, and detect drift.

Several documents in this repo have a twin on
``docs.clevelandbusinessmentors.org`` and carry a "keep the two in sync" note
whose only enforcement, until now, was somebody remembering. That already
failed once: ``training-guide.md`` was published saying the nightly reset was
"not yet switched on", and the reset was armed an hour later (2026-08-22).

``--check`` is the point of this script. ``--publish`` is the convenience.

**The site is PUBLICLY readable** — no login. Never publish credentials, live
usernames, or anything identifying real accounts. ``training-guide.md`` ships
its six sign-in usernames stripped for exactly that reason, and
:func:`for_publication` refuses to publish anything that still contains one.

**Not every twin can be auto-published.** ``data-model.md``'s published copy
replaces its mermaid blocks with PNGs exported by ``@mermaid-js/mermaid-cli``,
because that BookStack has no mermaid renderer — pushing the markdown over it
would destroy the diagrams. Those docs are ``check_only``: drift is reported,
publishing is refused.

Credentials come from ``.env`` (gitignored) and are never printed::

    BOOKSTACK_URL=https://docs.clevelandbusinessmentors.org
    BOOKSTACK_TOKEN_ID=...
    BOOKSTACK_TOKEN_SECRET=...

Usage::

    uv run python scripts/publish_docs.py                      # check all, exit 1 on drift
    uv run python scripts/publish_docs.py --list
    uv run python scripts/publish_docs.py --publish training-guide.md
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Anything matching this must never reach the public site.
FORBIDDEN = (
    re.compile(r"[\w.+-]+@cbmentors\.org"),          # live login addresses
    re.compile(r"BOOKSTACK_TOKEN|ESPO_API_KEY|password\s*[:=]\s*\S", re.I),
)


@dataclass(frozen=True)
class Doc:
    path: str
    book: str
    page: str
    #: True when the published copy differs from the markdown on purpose
    #: (images replacing diagrams, wording adapted for that audience). Drift is
    #: still reported; publishing is refused so the difference is not lost.
    check_only: bool = False
    note: str = ""


PUBLISHED: tuple[Doc, ...] = (
    Doc("training-guide.md", "Training Sandbox",
        "Running a training session on the sandbox"),
    Doc("data-model.md", "Data Model", "How the data is structured",
        check_only=True,
        note="HTML-authored page (editor=wysiwyg2024, no markdown source) whose "
             "mermaid blocks were replaced by PNGs — neither comparable nor safe "
             "to publish; sync by hand, or re-author it in markdown to make it "
             "checkable"),
    Doc("email-executive-summary.md", "Email Guide", "How Email Works",
        check_only=True,
        note="published copy was written for that site's audience; confirm the "
             "differences are deliberate before making this publishable"),
)


# --------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Read .env directly — these are developer credentials, not app settings,
    so they are deliberately absent from ``core.config.Settings``."""
    env = dict(os.environ)
    path = REPO / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    missing = [k for k in ("BOOKSTACK_URL", "BOOKSTACK_TOKEN_ID", "BOOKSTACK_TOKEN_SECRET")
               if not env.get(k)]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Put them in .env — see this script's docstring."
        )
    return env


class BookStack:
    def __init__(self, env: dict[str, str]) -> None:
        self.base = env["BOOKSTACK_URL"].rstrip("/")
        self._auth = f"Token {env['BOOKSTACK_TOKEN_ID']}:{env['BOOKSTACK_TOKEN_SECRET']}"

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base}{path}", data=body, method=method,
            headers={"Authorization": self._auth, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            # Never echo the request headers here — they carry the token.
            raise SystemExit(f"BookStack {method} {path} -> HTTP {exc.code}: {detail}")

    def find_book(self, name: str) -> dict | None:
        for book in self._call("GET", "/api/books?count=500").get("data", []):
            if book["name"] == name:
                return book
        return None

    def find_page(self, book_id: int, name: str) -> dict | None:
        query = urllib.parse.urlencode({"count": 500, "filter[book_id]": book_id})
        for page in self._call("GET", f"/api/pages?{query}").get("data", []):
            if page["name"] == name:
                return page
        return None

    def page_markdown(self, page_id: int) -> str:
        return self._call("GET", f"/api/pages/{page_id}").get("markdown") or ""

    def update_page(self, page_id: int, name: str, markdown: str) -> dict:
        return self._call("PUT", f"/api/pages/{page_id}",
                          {"name": name, "markdown": markdown})


# --------------------------------------------------------------------------

def for_publication(text: str) -> str:
    """The repo file as the site should see it.

    Strips the repo-only ``> Published to the docs site …`` block — it records
    where the twin lives and is meaningless on the twin itself.
    """
    lines, out, skipping = text.split("\n"), [], False
    for line in lines:
        if line.startswith("> Published to the docs site"):
            skipping = True
            continue
        if skipping:
            if line.startswith(">") or not line.strip():
                if not line.strip():
                    skipping = False
                continue
            skipping = False
        out.append(line)
    return "\n".join(out).strip() + "\n"


def normalise(text: str) -> str:
    """Compare on content, not on trailing whitespace or line endings."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def guard(doc: Doc, text: str) -> None:
    for pattern in FORBIDDEN:
        hit = pattern.search(text)
        if hit:
            raise SystemExit(
                f"REFUSING to publish {doc.path}: it contains {hit.group(0)!r}, and "
                f"{'that site is publicly readable' if '@' in hit.group(0) else 'that looks like a credential'}."
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publish", metavar="FILE",
                        help="push this document (default is check-only)")
    parser.add_argument("--list", action="store_true", help="show the manifest and exit")
    args = parser.parse_args()

    if args.list:
        for doc in PUBLISHED:
            flag = "check-only" if doc.check_only else "publishable"
            print(f"  {doc.path:28} -> {doc.book} / {doc.page}  [{flag}]")
            if doc.note:
                print(f"  {'':28}    {doc.note}")
        return 0

    api = BookStack(load_env())
    drifted = uncomparable = 0

    for doc in PUBLISHED:
        if args.publish and doc.path != args.publish:
            continue
        source = REPO / doc.path
        if not source.exists():
            print(f"[MISSING] {doc.path} is in the manifest but not on disk")
            drifted += 1
            continue

        wanted = for_publication(source.read_text(encoding="utf-8"))
        book = api.find_book(doc.book)
        page = api.find_page(book["id"], doc.page) if book else None
        if not page:
            print(f"[ABSENT ] {doc.path} -> {doc.book} / {doc.page} not found on the site")
            drifted += 1
            continue

        live = api.page_markdown(page["id"])
        # A page authored in the WYSIWYG editor stores no markdown at all, so
        # there is nothing to compare against. Say so rather than reporting
        # phantom drift for ever.
        if not live.strip():
            print(f"[no-md  ] {doc.path} -> {doc.book} / {doc.page} is HTML-authored; "
                  "markdown comparison is impossible")
            if doc.note:
                print(f"            {doc.note}")
            uncomparable += 1
            continue
        same = normalise(live) == normalise(wanted)

        if args.publish:
            if doc.check_only:
                print(f"[REFUSED] {doc.path}: {doc.note}")
                return 2
            guard(doc, wanted)
            if same:
                print(f"[SAME   ] {doc.path} already matches the site — nothing sent")
                return 0
            api.update_page(page["id"], doc.page, wanted)
            after = api.page_markdown(page["id"])
            ok = normalise(after) == normalise(wanted)
            print(f"[{'PUBLISHED' if ok else 'MISMATCH'}] {doc.path} -> "
                  f"{api.base}/books/{book['slug']}/page/{page['slug']}")
            return 0 if ok else 1

        if same:
            print(f"[ok     ] {doc.path}")
        else:
            drifted += 1
            marker = "drift, CHECK-ONLY" if doc.check_only else "drift"
            print(f"[{marker:>7}] {doc.path} differs from {doc.book} / {doc.page} "
                  f"({len(normalise(live))} chars live vs {len(normalise(wanted))} in repo)")
            if doc.note:
                print(f"            {doc.note}")

    if args.publish:
        print(f"No manifest entry for {args.publish!r} — try --list")
        return 2
    summary = f"\n{drifted} document(s) out of sync"
    if uncomparable:
        summary += f", {uncomparable} not comparable (HTML-authored on the site)"
    print(summary + ".")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
