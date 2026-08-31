"""A chapter with its own Google Workspace must not inherit Cleveland's mail
domain by accident — found on the Lakeside rehearsal (2026-08-31).

Two places used to hardcode ``cbmentors.org``: the address mentor logins are
minted in, and the "is this one of ours" check the comms pipeline runs on every
address. Both now read a setting whose DEFAULT is Cleveland's, so an
unconfigured deployment behaves exactly as before.
"""
from core.config import Settings, get_settings


def _install(monkeypatch, **overrides):
    s = Settings(**overrides)
    monkeypatch.setattr("core.config.get_settings", lambda: s)
    monkeypatch.setattr("mentoradmin.service.get_settings", lambda: s)
    monkeypatch.setattr("comms.service.get_settings", lambda: s)
    return s


def test_default_is_cleveland(monkeypatch):
    _install(monkeypatch)
    from mentoradmin.service import cbm_email_for
    from comms.service import _is_internal_address
    assert cbm_email_for("Jordan", "Mentor") == "jordan.mentor@cbmentors.org"
    assert _is_internal_address("someone@cbmentors.org")
    assert not _is_internal_address("someone@acmeconstruction.us")


def test_chapter_domain_is_a_setting(monkeypatch):
    _install(monkeypatch, mentor_email_domain="acmeconstruction.us",
             comms_internal_domains="acmeconstruction.us, lakeside.example")
    from mentoradmin.service import cbm_email_for
    from comms.service import _is_internal_address
    assert cbm_email_for("Jordan", "Mentor") == "jordan.mentor@acmeconstruction.us"
    assert _is_internal_address("info@acmeconstruction.us")
    assert _is_internal_address("Jordan.Mentor@LAKESIDE.EXAMPLE")
    assert not _is_internal_address("someone@cbmentors.org")
    assert not _is_internal_address("no-at-sign")
