"""The find-or-create-or-null-fill helper used by every form's Contact step."""

from __future__ import annotations

import pytest

from core.crm_upsert import find_create_or_fill


class FakeClient:
    def __init__(self, existing=None):
        self._existing = existing  # dict (the matched record) or None
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []

    async def create(self, entity, payload):
        self.creates.append((entity, payload))
        return {"id": "new-1", **payload}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}

    async def find_one(self, entity, attribute, value, select="id"):
        return self._existing


PAYLOAD = {
    "firstName": "Ada",
    "emailAddress": "ada@example.com",
    "phoneNumber": "+12165550100",
    "cHowDidYouHear": "Online Search",
    "cMarketingOptIn": True,
}
FILL = ("firstName", "phoneNumber", "cHowDidYouHear", "cMarketingOptIn")


@pytest.mark.asyncio
async def test_no_match_creates():
    c = FakeClient(existing=None)
    rid, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="ada@example.com",
        create_payload=PAYLOAD, fill_keys=FILL,
    )
    assert action == "created" and rid == "new-1"
    assert c.creates and not c.updates


@pytest.mark.asyncio
async def test_match_all_empty_fills_eligible_only():
    # Existing record has only an id (everything else null) -> fill all FILL keys,
    # but NEVER the excluded emailAddress (not in fill_keys).
    c = FakeClient(existing={"id": "c-9"})
    rid, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="ada@example.com",
        create_payload=PAYLOAD, fill_keys=FILL,
    )
    assert action == "updated" and rid == "c-9"
    (_, _, written), = c.updates
    assert set(written) == set(FILL)
    assert "emailAddress" not in written  # match key never back-written


@pytest.mark.asyncio
async def test_match_does_not_overwrite_non_empty():
    # phoneNumber + cHowDidYouHear already set on the record -> left untouched;
    # only the genuinely-empty fields are filled.
    c = FakeClient(existing={
        "id": "c-9", "phoneNumber": "+1999", "cHowDidYouHear": "Personal Referral",
        "firstName": "", "cMarketingOptIn": None,
    })
    _, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="ada@example.com",
        create_payload=PAYLOAD, fill_keys=FILL,
    )
    assert action == "updated"
    (_, _, written), = c.updates
    assert written == {"firstName": "Ada", "cMarketingOptIn": True}


@pytest.mark.asyncio
async def test_match_nothing_to_fill_is_a_noop():
    c = FakeClient(existing={
        "id": "c-9", "firstName": "Ada", "phoneNumber": "+1999",
        "cHowDidYouHear": "Other", "cMarketingOptIn": False,
    })
    _, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="ada@example.com",
        create_payload=PAYLOAD, fill_keys=FILL,
    )
    assert action == "matched"
    assert not c.updates  # a stored False is a real value, not a null to fill


@pytest.mark.asyncio
async def test_empty_desired_value_is_never_written():
    # A null-fill never writes an empty desired value over an empty stored one.
    c = FakeClient(existing={"id": "c-9"})
    _, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="x@example.com",
        create_payload={"firstName": "", "phoneNumber": None}, fill_keys=("firstName", "phoneNumber"),
    )
    assert action == "matched" and not c.updates
