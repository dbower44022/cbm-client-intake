"""Offline guards for the docs publisher.

The publisher talks to a live site, so the network path is not tested here.
What IS tested is the part that would quietly do damage: the transform that
decides what the public site receives, and the guard that stops a credential
reaching a page anyone can read without logging in.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "publish_docs", REPO / "scripts" / "publish_docs.py"
)
assert _spec and _spec.loader
publish_docs = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves the decorated class's __module__
# through sys.modules, and an unregistered module makes that lookup return None.
sys.modules[_spec.name] = publish_docs
_spec.loader.exec_module(publish_docs)


def test_every_manifest_file_exists():
    """A renamed or deleted doc must fail here, not on the next publish."""
    missing = [d.path for d in publish_docs.PUBLISHED if not (REPO / d.path).exists()]
    assert not missing, f"in the manifest but not on disk: {missing}"


def test_the_repo_only_header_is_stripped():
    """The `> Published to the docs site` block records where the twin lives and
    is meaningless on the twin itself."""
    source = (
        "# Title\n\n"
        "> Published to the docs site 2026-08-22:\n"
        "> https://example.org/books/x/page/y\n"
        "> **Keep the two in sync.**\n\n"
        "Body text.\n"
    )
    out = publish_docs.for_publication(source)
    assert "Published to the docs site" not in out
    assert out.startswith("# Title")
    assert "Body text." in out


def test_a_document_without_the_header_is_unchanged():
    source = "# Title\n\nBody text.\n"
    assert publish_docs.for_publication(source).strip() == source.strip()


def test_publishing_a_live_username_is_refused():
    """The site is readable without signing in. A page listing real accounts on
    an internet-facing CRM is the mistake this exists to prevent."""
    doc = publish_docs.Doc("x.md", "Book", "Page")
    with pytest.raises(SystemExit) as excinfo:
        publish_docs.guard(doc, "Sign in as joe.mentor@cbmentors.org")
    assert "REFUSING" in str(excinfo.value)


def test_publishing_a_credential_is_refused():
    doc = publish_docs.Doc("x.md", "Book", "Page")
    with pytest.raises(SystemExit):
        publish_docs.guard(doc, "set ESPO_API_KEY = abcdef123456")


def test_ordinary_prose_passes_the_guard():
    publish_docs.guard(publish_docs.Doc("x.md", "B", "P"),
                       "Sign in as Joe Mentor. Ask an administrator for the address.")


def test_the_published_training_guide_carries_no_usernames():
    """The real document, not a fixture — this is the one that goes public."""
    text = publish_docs.for_publication(
        (REPO / "training-guide.md").read_text(encoding="utf-8")
    )
    publish_docs.guard(publish_docs.PUBLISHED[0], text)


def test_check_only_docs_carry_a_reason():
    """A refusal with no explanation just looks like a bug."""
    for doc in publish_docs.PUBLISHED:
        if doc.check_only:
            assert doc.note, f"{doc.path} is check_only with no note"
