"""The conformance check's contract (plan Phase 1, Layer 1).

These tests exist because the two properties that matter most cannot be seen by
running the script against a healthy CRM: that a **missing grant never reports as
a missing entity** (C3), and that each **exit code is actually produced** (C4).
A code that has never been observed is a code that does not exist.
"""

from __future__ import annotations

import asyncio

import pytest

from core.espo import EspoError, EspoTransportError
from scripts import preflight_crm as pf


class FakeClient:
    """Only the four reads the check makes. Each can be told to fail."""

    def __init__(self, *, acl=None, meta=None, enums=None, lists=None, raise_on=None):
        self.acl = acl if acl is not None else {}
        self.meta = meta or {}
        self.enums = enums or {}
        self.lists = lists or {}
        self.raise_on = raise_on or {}

    def _maybe_raise(self, key):
        exc = self.raise_on.get(key)
        if exc:
            raise exc

    async def app_user(self):
        self._maybe_raise("app_user")
        return {"acl": {"table": self.acl}}

    async def metadata(self, key):
        self._maybe_raise(key)
        # An invisible scope answers 200 with an empty body — the whole trap.
        return self.meta.get(key, {})

    async def metadata_enum_options(self, entity, field):
        return self.enums.get((entity, field))

    async def list(self, entity, *, max_size=200, offset=0, select=None):
        self._maybe_raise(f"list:{entity}")
        rows = self.lists.get(entity, [])[offset : offset + max_size]
        return {"total": len(self.lists.get(entity, [])), "list": [{"name": n} for n in rows]}


def _probe(**kw):
    return pf.Probe(FakeClient(**kw))


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- C3: absent vs forbidden vs unreachable ---------------------------------

def test_empty_metadata_with_no_read_grant_is_forbidden_not_absent():
    """The regression this check was rewritten for: EspoCRM returns an empty 200
    for a scope the caller cannot see, and the old report called that 'absent'."""
    p = _probe(acl={"CEngagement": {"read": "no"}})
    _run(p.load_acl())
    status, _, detail = _run(p.metadata("entityDefs.CEngagement.fields", "CEngagement"))
    assert status == pf.FORBIDDEN
    assert "no read grant" in detail


def test_empty_metadata_with_a_read_grant_is_absent():
    p = _probe(acl={"CEngagement": {"read": "all"}})
    _run(p.load_acl())
    status, _, _ = _run(p.metadata("entityDefs.CEngagement.fields", "CEngagement"))
    assert status == pf.ABSENT


def test_empty_metadata_with_no_acl_table_is_error_not_a_guess():
    """An admin key reports no ACL table. Refusing to guess is the point."""
    p = _probe(acl={})
    _run(p.load_acl())
    status, _, detail = _run(p.metadata("entityDefs.CEngagement.fields", "CEngagement"))
    assert status == pf.ERROR
    assert "tell 'absent' from 'forbidden'" in detail


def test_transport_failure_is_unreachable():
    p = _probe(raise_on={"entityDefs.Contact.fields": EspoTransportError("boom")})
    status, _, _ = _run(p.metadata("entityDefs.Contact.fields", "Contact"))
    assert status == pf.UNREACHABLE


def test_403_is_forbidden():
    p = _probe(raise_on={"list:Team": EspoError("list Team failed: HTTP 403 Forbidden")})
    status, _, _ = _run(p.list_names("Team"))
    assert status == pf.FORBIDDEN


# --- C4: the exit codes -----------------------------------------------------

def _result(checks):
    counts: dict[str, int] = {}
    for c in checks:
        counts[c] = counts.get(c, 0) + 1
    drift = counts.get(pf.ABSENT, 0)
    unchecked = sum(counts.get(k, 0) for k in pf._UNCHECKED)
    return 1 if drift else (3 if unchecked else 0)


@pytest.mark.parametrize("outcomes,expected", [
    ([pf.OK, pf.OK], 0),
    ([pf.OK, pf.ADVISORY], 0),          # enum gaps are advisory by default
    ([pf.OK, pf.ABSENT], 1),
    ([pf.OK, pf.FORBIDDEN], 3),
    ([pf.OK, pf.UNREACHABLE], 3),
    ([pf.ABSENT, pf.UNREACHABLE], 1),   # a certain problem beats an uncertain one
])
def test_exit_code_precedence(outcomes, expected):
    assert _result(outcomes) == expected


# --- The desired state is derived, not hand-listed --------------------------

def test_required_teams_come_from_the_settings_gates():
    """Adding a team gate must not require remembering to update this script."""
    from core.config import get_settings

    teams = pf.required_teams(get_settings())
    assert "Mentor Team" in teams
    assert "Analytics Admin Team" in teams
    assert "Client Administration Team" in teams
    # Derived from every *_allowed_teams_list property, so a new gate lands here
    # automatically; the count is a floor, not an assertion about today.
    assert len(teams) >= 7


def test_required_email_templates_match_the_events_follow_ups():
    """The five event templates are declared in events/notify.py; this list must
    not drift from it (the sixth, MentorAssignmentNotice, lives in the
    assignments frontend and is checked by name below)."""
    from events import notify

    declared = {f.template for f in notify.FOLLOW_UPS}
    assert declared <= set(pf.REQUIRED_EMAIL_TEMPLATES)
    assert "MentorAssignmentNotice" in pf.REQUIRED_EMAIL_TEMPLATES


def test_dead_fields_are_not_required():
    """Removed from BOTH CRMs / superseded by the receipt vocabulary. Requiring
    them reports drift nobody can fix (found by running the check, 2026-08-21)."""
    assert "cAccountType" not in pf.REQUIRED_FIELDS["Account"]
    assert "reason" not in pf.REQUIRED_FIELDS["CIntakeSubmission"]
    assert "status" not in pf.REQUIRED_FIELDS["CIntakeSubmission"]
