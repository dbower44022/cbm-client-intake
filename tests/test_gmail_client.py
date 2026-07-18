"""GmailClient transport hardening (P1-5 F4, reliability review 2026-07-17):
bounded 429/5xx backoff with Retry-After, shared connection, and a
no-retry + roomy-timeout send (non-idempotent — a retry could double-send)."""

from __future__ import annotations

import httpx
import pytest

from core import gmail as gm


class FakeHttp:
    """Stands in for the client's shared httpx.AsyncClient."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # (method, url, timeout)

    is_closed = False

    async def request(self, method, url, **kw):
        self.calls.append((method, url, kw.get("timeout")))
        return self.responses.pop(0)


def _client(responses):
    client = gm.GmailClient({"fake": "sa"}, "bob.mentor@cbmentors.org")

    async def token(scope):
        return "tok"

    client._token = token
    client._http = FakeHttp(responses)
    return client


def _resp(status, body=b"{}", headers=None):
    return httpx.Response(status, content=body, headers=headers or {})


async def test_read_retries_429_with_retry_after():
    client = _client([
        _resp(429, headers={"retry-after": "0"}),
        _resp(200, body=b'{"ok": 1}'),
    ])
    out = await client._request("GET", "/profile")
    assert out == {"ok": 1}
    assert len(client._http.calls) == 2


async def test_read_retries_5xx_then_gives_up_bounded():
    client = _client([_resp(500)] * 10)
    with pytest.raises(gm.GmailError, match="HTTP 500"):
        await client._request("GET", "/profile")
    assert len(client._http.calls) == gm._MAX_ATTEMPTS  # bounded, not 10


async def test_4xx_is_never_retried():
    client = _client([_resp(403), _resp(200)])
    with pytest.raises(gm.GmailError, match="HTTP 403"):
        await client._request("GET", "/profile")
    assert len(client._http.calls) == 1


async def test_history_404_still_raises_expired():
    client = _client([_resp(404)])
    with pytest.raises(gm.HistoryExpiredError):
        await client._request("GET", "/history")


async def test_send_is_not_retried_and_uses_the_send_timeout():
    """A send 5xx is ambiguous (Gmail may have committed) — retrying could
    double-send. The send also gets its own roomy timeout for large bodies."""
    from email.message import EmailMessage

    client = _client([_resp(500)])
    msg = EmailMessage()
    msg["From"] = "bob.mentor@cbmentors.org"
    msg["To"] = "a@b.test"
    msg.set_content("hi")
    with pytest.raises(gm.GmailError, match="HTTP 500"):
        await client.send(msg)
    assert len(client._http.calls) == 1  # no retry
    assert client._http.calls[0][2] == gm.SEND_TIMEOUT_SECONDS


async def test_shared_client_reused_across_calls():
    client = _client([_resp(200), _resp(200)])
    http = client._client()
    await client._request("GET", "/profile")
    await client._request("GET", "/profile")
    assert client._client() is http  # one connection pool, not one per call
