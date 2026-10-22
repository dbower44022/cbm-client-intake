"""Ruling 70 (10-21-26): an engagement's close date is stamped when it closes —
only when empty, never over a typed date, and not at all while the CRM still
holds the field Read-only."""

from __future__ import annotations

import asyncio

from core import engagement_close as ec


class Crm:
    def __init__(self, *, read_only=False, close=None):
        self.read_only = read_only
        self.row = {"id": "E1", "closeDate": close}
        self.updates = []

    async def metadata(self, key):
        return {"closeDate": {"type": "date", **({"readOnly": True} if self.read_only else {})}}

    async def get(self, entity, rid, select=None):
        return dict(self.row)

    async def update(self, entity, rid, payload):
        self.updates.append(payload)
        self.row.update(payload)


def run(c):
    return asyncio.run(c)


def test_a_closing_status_stamps_today():
    crm = Crm()
    day = run(ec.stamp_close_date(crm, "E1", "Completed"))
    assert day and crm.updates == [{"closeDate": day}]


def test_an_open_status_stamps_nothing():
    crm = Crm()
    assert run(ec.stamp_close_date(crm, "E1", "Active")) is None and crm.updates == []


def test_a_held_date_is_never_overwritten():
    crm = Crm(close="2025-06-30")
    assert run(ec.stamp_close_date(crm, "E1", "Inactive")) is None and crm.updates == []


def test_a_date_typed_in_the_same_save_wins():
    crm = Crm()
    assert run(ec.stamp_close_date(crm, "E1", "Abandoned", payload={"closeDate": "2026-10-01"})) is None


def test_nothing_while_the_field_is_read_only():
    crm = Crm(read_only=True)
    assert run(ec.stamp_close_date(crm, "E1", "Completed")) is None and crm.updates == []
