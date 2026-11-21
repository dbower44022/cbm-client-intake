"""The courses this application serves (prds/training-app-plan.md, decision 3).

A course is a folder under ``training/`` holding its Markdown and a small
``course.yaml``::

    id: evaluation-demo
    title: Business Evaluation — the training demo
    minutes: 90
    markdown: evaluation-demo.md
    applications: [assignments, mentorsessions, mentoradmin]
    onboarding: mentor        # optional (TR10, phase 4)

The revision is read from the Markdown's ``Last Updated`` line only, so it
has one source. Courses are read once per process, at first use, which is
start-up in practice; a course reaches a chapter with the release that
carries it (TR4). A malformed ``course.yaml`` is logged and left out, never
fatal.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from . import render

log = logging.getLogger("cbm_intake.courses")

#: ``training/`` beside this package, which the image carries.
TRAINING_DIR = Path(__file__).resolve().parent.parent / "training"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
#: Words the course routes use for pages of their own (plan decision 2).
RESERVED_IDS = frozenset({"report", "assets", "api", "mine"})


@dataclass(frozen=True)
class Course:
    id: str
    title: str
    minutes: int
    applications: tuple[str, ...]
    markdown: Path
    revision: str               # "N.M"
    onboarding: str = ""
    #: The change log, revision to entry (TR4's returning reminder).
    changes: dict = field(default_factory=dict, compare=False, repr=False)
    doc: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def major(self) -> int:
        """N of N.M: the significant revision (TR4)."""
        return major_of(self.revision)

    @property
    def draft(self) -> bool:
        """A course at 0.x records completion but never comes due (decision 9)."""
        return self.major == 0

    @property
    def items(self) -> list[dict]:
        return render.items(self.doc)


def major_of(revision: str) -> int:
    try:
        return int(str(revision).split(".", 1)[0])
    except ValueError:
        return 0


def load_course(folder: Path) -> Optional[Course]:
    """One folder's course, or None (logged) when it is not a valid course."""
    meta_path = folder / "course.yaml"
    try:
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("courses: %s could not be read: %s", meta_path, exc)
        return None
    if not isinstance(meta, dict):
        log.warning("courses: %s is not a mapping", meta_path)
        return None
    cid = str(meta.get("id") or "").strip()
    if not ID_RE.match(cid) or cid in RESERVED_IDS:
        log.warning("courses: %s has an unusable id %r", meta_path, cid)
        return None
    md_name = str(meta.get("markdown") or "").strip()
    if not md_name:
        mds = sorted(folder.glob("*.md"))
        md_name = mds[0].name if len(mds) == 1 else ""
    md_path = folder / md_name if md_name else None
    if md_path is None or not md_path.is_file():
        log.warning("courses: %s names no Markdown file that exists", meta_path)
        return None
    md_text = md_path.read_text(encoding="utf-8")
    doc = render.parse(md_text)
    revision = render.revision_number(doc)
    if not revision:
        log.warning("courses: %s has no 'Revision N.M' on its Last Updated line", md_path)
        return None
    apps = meta.get("applications") or []
    if isinstance(apps, str):
        apps = [a for a in re.split(r"[,\s]+", apps) if a]
    apps = tuple(str(a).strip().strip("/") for a in apps if str(a).strip())
    if not apps:
        log.warning("courses: %s lists no applications", meta_path)
        return None
    try:
        minutes = int(meta.get("minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0
    return Course(id=cid, title=str(meta.get("title") or doc["title"]).strip(),
                  minutes=minutes, applications=apps, markdown=md_path, revision=revision,
                  onboarding=str(meta.get("onboarding") or "").strip(),
                  changes=render.change_log(md_text), doc=doc)


def discover(root: Path = TRAINING_DIR) -> dict[str, Course]:
    """Every course under ``root``, by id, in folder order. A second course
    with an id already taken is logged and left out."""
    out: dict[str, Course] = {}
    for meta_path in sorted(root.glob("*/course.yaml")):
        course = load_course(meta_path.parent)
        if course is None:
            continue
        if course.id in out:
            log.warning("courses: %s repeats the id %r; left out", meta_path, course.id)
            continue
        out[course.id] = course
    return out


@lru_cache(maxsize=1)
def catalog() -> dict[str, Course]:
    """The courses, read once per process."""
    courses = discover()
    log.info("courses: %d found (%s)", len(courses), ", ".join(courses) or "none")
    return courses
