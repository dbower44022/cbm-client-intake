"""V2 Phase 1: the ResumableClient skips work already recorded in progress."""

from __future__ import annotations

from core.resumable import ResumableClient


class RecordingClient:
    def __init__(self) -> None:
        self.creates: list[str] = []
        self.uploads = 0
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append(entity)
        return {"id": f"{entity}-{self._n}", **payload}

    async def find_one(self, *a, **k):
        return None

    async def update(self, *a, **k):
        return {}

    async def relate(self, *a, **k):
        return None

    async def upload_attachment(self, **k):
        self.uploads += 1
        return f"att-{self.uploads}"


async def test_records_then_skips_creates_on_replay():
    inner = RecordingClient()
    saved: dict = {}

    async def save(p):
        saved.clear()
        saved.update(p)

    c = ResumableClient(inner, {}, save)
    a = await c.create("Account", {"name": "X"})
    co = await c.create("Contact", {"x": 1})
    assert inner.creates == ["Account", "Contact"]
    assert saved == {"create:Account#1": a["id"], "create:Contact#1": co["id"]}

    # Replay with the saved progress: nothing is created, recorded ids returned.
    inner2 = RecordingClient()
    c2 = ResumableClient(inner2, dict(saved), None)
    a2 = await c2.create("Account", {"name": "X"})
    co2 = await c2.create("Contact", {"x": 1})
    assert inner2.creates == []
    assert a2["id"] == a["id"]
    assert co2["id"] == co["id"]


async def test_resume_completes_only_the_missing_step():
    inner = RecordingClient()
    saved: dict = {}

    async def save(p):
        saved.clear()
        saved.update(p)

    # First run gets through Account + Contact, then "fails".
    c = ResumableClient(inner, {}, save)
    await c.create("Account", {})
    await c.create("Contact", {})

    # Retry: Account/Contact are skipped; only the missing CClientProfile is created.
    inner2 = RecordingClient()
    c2 = ResumableClient(inner2, dict(saved), None)
    await c2.create("Account", {})
    await c2.create("Contact", {})
    await c2.create("CClientProfile", {})
    assert inner2.creates == ["CClientProfile"]


async def test_uploads_are_skipped_on_replay():
    inner = RecordingClient()
    saved: dict = {}

    async def save(p):
        saved.clear()
        saved.update(p)

    c = ResumableClient(inner, {}, save)
    first = await c.upload_attachment(filename="r.pdf", content_type="application/pdf",
                                      data_base64="x", related_type="CMentorProfile", field="resumeUpload")
    assert inner.uploads == 1

    inner2 = RecordingClient()
    c2 = ResumableClient(inner2, dict(saved), None)
    again = await c2.upload_attachment(filename="r.pdf", content_type="application/pdf",
                                       data_base64="x", related_type="CMentorProfile", field="resumeUpload")
    assert inner2.uploads == 0  # not re-uploaded
    assert again == first
