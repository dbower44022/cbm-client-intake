"""Invented training addresses never leave the system (core/sandbox_addresses.py).

Association ruling 77: the Association's system is a real chapter AND the
training system, so its shared mailbox, Drive and group stay on and these
four guards keep the invented addresses in. Empty setting = no effect.
"""

from __future__ import annotations

import asyncio
from email.message import EmailMessage

import pytest

from core import mailing_sync as sync
from core.config import Settings, get_settings
from core.gdrive import DriveClient, DriveNoAccountError
from core.gmail import GmailClient, GmailError, SandboxAddressRefused
from core.google_directory import GoogleDirectory, GoogleDirectoryError
from core.sandbox_addresses import is_sandbox_address, sandbox_domain, sandbox_recipients

from tests.test_mailing_sync import FakeCRM, FakeMail, contact, vendor

DOMAIN = "sandbox.mentorsassociation.org"


@pytest.fixture
def invented(monkeypatch):
    monkeypatch.setenv("SANDBOX_ADDRESS_DOMAIN", DOMAIN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_domain(monkeypatch):
    monkeypatch.delenv("SANDBOX_ADDRESS_DOMAIN", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_matching_is_the_domain_and_its_subdomains_only():
    assert is_sandbox_address("joe.mentor@sandbox.mentorsassociation.org", DOMAIN)
    assert is_sandbox_address("Info@Brightline.Sandbox.MentorsAssociation.org", DOMAIN)
    assert not is_sandbox_address("info@mentorsassociation.org", DOMAIN)
    assert not is_sandbox_address("x@notsandbox.mentorsassociation.org", DOMAIN)
    assert not is_sandbox_address("x@sandbox.mentorsassociation.org.evil.com", DOMAIN)
    assert not is_sandbox_address("joe.mentor@sandbox.mentorsassociation.org", "")
    assert sandbox_recipients(["Dana <dana@sandbox.mentorsassociation.org>, real@x.org"], DOMAIN) \
        == ["dana@sandbox.mentorsassociation.org"]


def test_the_setting_defaults_to_empty_and_is_on_the_settings_page(no_domain):
    from core.settings_registry import SETTINGS

    assert Settings().sandbox_address_domain == ""
    assert sandbox_domain() == ""
    assert any(s.key == "sandbox_address_domain" for s in SETTINGS)


def _mime(to: str, cc: str = "") -> EmailMessage:
    m = EmailMessage()
    m["From"] = "info@mentorsassociation.org"
    m["To"] = to
    if cc:
        m["Cc"] = cc
    m["Subject"] = "hello"
    m.set_content("hi")
    return m


def test_gmail_refuses_an_invented_recipient_before_calling_google(invented):
    gmail = GmailClient({}, "info@mentorsassociation.org")

    async def boom(*a, **kw):  # any call to Google fails the test
        raise AssertionError("reached Google")

    gmail._request = boom  # type: ignore[assignment]
    with pytest.raises(SandboxAddressRefused) as exc:
        asyncio.run(gmail.send(_mime("real@x.org", cc=f"dana.whitcomb@{DOMAIN}")))
    assert isinstance(exc.value, GmailError)
    assert f"dana.whitcomb@{DOMAIN}" in str(exc.value) and "invented training address" in str(exc.value)


def test_gmail_sends_normally_when_no_domain_is_set(no_domain):
    gmail = GmailClient({}, "info@mentorsassociation.org")
    calls = []

    async def fake(*a, **kw):
        calls.append(a)
        return {"id": "m1"}

    gmail._request = fake  # type: ignore[assignment]
    assert asyncio.run(gmail.send(_mime(f"dana@{DOMAIN}")))["id"] == "m1"
    assert calls


def test_drive_never_shares_with_an_invented_address(invented):
    drive = DriveClient({}, "svc@x.org", "drive1")

    async def boom(*a, **kw):
        raise AssertionError("reached Google")

    drive._send = boom  # type: ignore[assignment]
    with pytest.raises(DriveNoAccountError):  # the grant engine's "not possible", never "failed"
        asyncio.run(drive.create_permission("folder1", f"joe.mentor@{DOMAIN}"))


def test_the_group_never_gains_an_invented_address(invented):
    directory = GoogleDirectory({}, "doug.bower@mentorsassociation.org")
    with pytest.raises(GoogleDirectoryError, match="invented training address"):
        asyncio.run(directory.add_group_member("allmembers@mentorsassociation.org",
                                               f"joe.mentor@{DOMAIN}"))


async def test_the_mailing_list_leaves_invented_addresses_out_and_removes_one_already_there(invented):
    crm = FakeCRM([contact("c1", "a@x.org"), contact("c2", f"rosa.medina@{DOMAIN}")])
    mail = FakeMail(lists=[{"list_id": "L1", "name": "Event notices"}],
                    members=[vendor("v-old", f"pavel.novak@{DOMAIN}")])
    plan = await sync.build_plan(crm, mail, "Event notices")
    assert [p.email for p in plan.add] == ["a@x.org"]
    assert [m.email for m in plan.remove] == [f"pavel.novak@{DOMAIN}"]


def test_the_demo_links_job_is_allowed_where_a_sandbox_domain_is_set():
    from campaigns import sandbox_demo as demo
    from core.sandbox_reset import SandboxResetRefused

    elsewhere = Settings(espo_base_url="https://crm.businessmentorsassociation.org",
                         espo_api_key="k", espo_dry_run=False)
    with pytest.raises(SandboxResetRefused):
        demo._parts(elsewhere)
    marked = Settings(espo_base_url="https://crm.businessmentorsassociation.org",
                      espo_api_key="k", espo_dry_run=False, sandbox_address_domain=DOMAIN)
    try:
        demo._parts(marked)
    except SandboxResetRefused:  # pragma: no cover - the failure being tested
        pytest.fail("refused a deployment that names a sandbox address domain")
    except RuntimeError:
        pass  # no database in a test: past the refusal, which is the point
