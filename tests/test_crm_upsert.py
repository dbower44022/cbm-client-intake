"""The find-or-create-or-null-fill helper used by every form's Contact step."""

from __future__ import annotations

import pytest

from core.crm_upsert import create_dropping_invalid, find_create_or_fill
from core.espo import EspoError


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


# --- a CRM-rejected droppable value must not sink the whole submission -------
#
# Live prod case (2026-06-30): a sponsor applicant typed the junk phone
# "123123213332". It passes core.phone.e164_or_none (10-15 digits) but EspoCRM
# rejected it with validationFailure/phoneNumber/valid, so the Contact create
# 400'd, the whole intake landed in needs_attention, and the alert then emailed
# admin@ hourly for a month. The lead matters more than the phone number.

class RejectingClient(FakeClient):
    """Rejects a named field's value once, the way EspoCRM does."""

    def __init__(self, field="phoneNumber", rule="valid", rejections=1):
        super().__init__(existing=None)
        self._field, self._rule = field, rule
        self._left = rejections

    async def create(self, entity, payload):
        if self._left and self._field in payload:
            self._left -= 1
            self.creates.append((entity, dict(payload)))  # snapshot: the caller reuses the dict
            raise EspoError(
                f'create {entity} failed: HTTP 400 {{"messageTranslation":'
                f'{{"label":"validationFailure","scope":null,"data":'
                f'{{"field":"{self._field}","type":"{self._rule}"}}}}}}'
            )
        return await super().create(entity, payload)


@pytest.mark.asyncio
async def test_rejected_phone_is_dropped_and_the_contact_is_still_created():
    c = RejectingClient()
    created = await create_dropping_invalid(c, "Contact", dict(PAYLOAD))
    assert created["id"] == "new-1"
    (_, first), (_, second) = c.creates
    assert "phoneNumber" in first and "phoneNumber" not in second
    assert second["emailAddress"] == "ada@example.com"  # the lead survives intact


@pytest.mark.asyncio
async def test_find_create_or_fill_survives_a_rejected_phone():
    c = RejectingClient()
    record_id, action = await find_create_or_fill(
        c, "Contact", match_attr="emailAddress", match_value="ada@example.com",
        create_payload=dict(PAYLOAD), fill_keys=FILL,
    )
    assert (record_id, action) == ("new-1", "created")


@pytest.mark.asyncio
async def test_a_rejected_identity_field_still_fails():
    # Only listed droppable fields are sacrificed — never the match key, a link,
    # or a discriminator, whose loss would create the wrong record.
    c = RejectingClient(field="emailAddress", rejections=99)
    with pytest.raises(EspoError):
        await create_dropping_invalid(c, "Contact", dict(PAYLOAD))


@pytest.mark.asyncio
async def test_a_required_failure_is_not_retried():
    # Dropping a field the CRM says is REQUIRED cannot help; surface the error.
    c = RejectingClient(rule="required", rejections=99)
    with pytest.raises(EspoError):
        await create_dropping_invalid(c, "Contact", dict(PAYLOAD))
    assert len(c.creates) == 1  # no pointless retry
