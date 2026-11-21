"""An in-memory twin of ``courses/store.CourseStore`` for the course tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryCourseStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []

    async def progress(self, user_id: str, course_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows if r["user_id"] == user_id and r["course_id"] == course_id]

    async def progress_counts(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in self.rows:
            if r["user_id"] == user_id:
                out.setdefault(r["course_id"], []).append(dict(r))
        return out

    async def save_item(self, user_id: str, course_id: str, revision: str, item_key: str,
                        answer: Optional[str] = None, now: Optional[datetime] = None) -> dict:
        now = now or _now()
        for r in self.rows:
            if (r["user_id"], r["course_id"], r["item_key"]) == (user_id, course_id, item_key):
                r.update(revision=revision, done_at=now, answer=answer)
                return dict(r)
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "course_id": course_id,
               "revision": revision, "item_key": item_key, "done_at": now, "answer": answer}
        self.rows.append(row)
        return dict(row)

    async def clear_item(self, user_id: str, course_id: str, item_key: str) -> None:
        await self.clear_items(user_id, course_id, [item_key])

    async def clear_items(self, user_id: str, course_id: str, item_keys: list[str]) -> None:
        self.rows = [r for r in self.rows if not (
            r["user_id"] == user_id and r["course_id"] == course_id and r["item_key"] in item_keys)]

    async def complete(self, user_id: str, user_name: str, course_id: str, revision: str,
                       answers: dict, now: Optional[datetime] = None) -> tuple[dict, bool]:
        for r in self.done:
            if (r["user_id"], r["course_id"], r["revision"]) == (user_id, course_id, revision):
                return dict(r), False
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "user_name": user_name,
               "course_id": course_id, "revision": revision, "completed_at": now or _now(),
               "answers": answers}
        self.done.append(row)
        return dict(row), True

    async def completions(self, user_id: str) -> list[dict[str, Any]]:
        return sorted((dict(r) for r in self.done if r["user_id"] == user_id),
                      key=lambda r: r["completed_at"], reverse=True)
