"""Track D D2 — the Follow-up tab in Event Administration, and the email ledger
on the Registrants tab. Guard tests over the served page and the payloads the
tab reads; the send itself is covered in test_events_notify.py."""
from __future__ import annotations

from pathlib import Path

from events import config as cfg
from events import confirm, notify

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "events" / "frontend" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "events" / "frontend" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "events" / "frontend" / "styles.css").read_text(encoding="utf-8")


def test_the_detail_view_has_a_follow_up_tab_and_panel():
    assert 'data-tab="followups"' in PAGE
    assert 'data-panel="followups"' in PAGE
    assert 'id="fuCards"' in PAGE and 'id="fuNote"' in PAGE


def test_the_registrants_table_has_an_emails_column():
    head = PAGE[PAGE.index('data-panel="registrants"'):PAGE.index('id="regRows"')]
    assert "<th>Emails</th>" in head
    assert "function ledgerCell" in APP and "confirmationSentAt" in APP


def test_the_registration_read_carries_the_ledgers():
    assert "followUpsSent" in cfg.REGISTRATION_SELECT
    assert "confirmationSentAt" in cfg.REGISTRATION_SELECT


def test_preview_is_the_default_and_send_is_a_second_named_click():
    # The tab posts preview:true first; a send is preview:false, and only after
    # a preview has named the count (never a one-click blast).
    assert '{ kind: kind.kind, preview: true }' in APP
    assert '{ kind: kind.kind, preview: false }' in APP
    assert "if (!planned)" in APP
    assert "disabled = true" not in APP[APP.index("function followUpCard"):APP.index("function rowButton")]


def test_the_catalogue_names_every_kind_the_tab_offers():
    kinds = {k["kind"] for k in notify.catalogue()}
    assert kinds == {notify.KIND_REMINDER, notify.KIND_RECORDING, notify.KIND_NO_SHOW,
                     notify.KIND_MENTOR_CTA, notify.KIND_SURVEY}
    assert all(k["template"].startswith("Event") for k in notify.catalogue())
    assert {c["template"] for c in confirm.catalogue()} == {
        "EventConfirmation", "EventWaitlisted", "EventSeatOffered"}


def test_the_tab_has_its_styles():
    for cls in (".ev__fu ", ".ev__fu-cards", ".ev__fu-actions", ".ev__ledger"):
        assert cls in CSS
