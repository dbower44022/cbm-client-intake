"""The Constant Contact send report (build plan § 7e.9, ruling 96; step M9).

For each email campaign whose sent email has been picked (it is Running and
carries ``vendorEmailId``), the report is read for its first
:data:`REPORT_DAYS` days: who it was sent to, who bounced, who opened and who
clicked. Each recipient becomes one ``COutreachTouch`` on the campaign,
matched to their Contact, updated in place on every read — so "who was
emailed" is exact and a second read never doubles a row.

- **Sent** becomes ``Delivered`` unless the address bounced, which is
  ``Returned`` with ``returnedAt`` and the bounce code in ``vendorStatus``.
  Constant Contact reports no per-person delivery time, so ``deliveredAt`` is
  left empty.
- **Opens** go to ``openCount`` / ``firstOpenedAt`` (Doug's ruling at the M9
  plan, 10-27-26), feature-detected: a CRM without them records the rest.
- **Clicks** go to ``clickCount`` / ``firstClickedAt``, and an empty outcome
  becomes ``Clicked``. A human outcome is never overwritten.
- **Matching.** A recipient's address is matched to a Contact through the
  campaign's own list first (a chapter member is emailed at their chapter
  address), then by the Contact's email, then by a mentor profile's chapter
  address. Someone who matches nothing is counted and named, never created.

Every vendor shape here is **inferred** from the vendor's V3 reference and
not yet called (the M9 live pass is the check):
``GET /reports/email_reports/{campaign_activity_id}/tracking/{sends|bounces|opens|clicks}``,
each a page of ``tracking_activities`` with ``email_address``,
``created_time`` and, for a bounce, ``bounce_code``.

Writes run under the org-wide API key. Behind ``CAMPAIGN_SEND_REPORT``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.campaigns.send_report")

#: The report is read for this many days after the email was picked; then
#: the campaign completes.
REPORT_DAYS = 30
TRACKING_KINDS = ("sends", "bounces", "opens", "clicks")
TRACKING_PAGE = 500
#: The touch fields the report may write beyond the Phase 1 ones.
OPEN_FIELDS = ("openCount", "firstOpenedAt")
REPORT_SELECT_BASE = ("id,name,channel,touchStatus,outcome,sentAt,returnedAt,vendorPieceId,vendorStatus,"
                      "contactId,clickCount,firstClickedAt")
#: A web request's *Read the report now* writes at most this many touches;
#: the nightly pass finishes the rest.
WEB_WRITE_CAP = 300
_ID_BATCH = 100


@dataclass
class Recipient:
    """One address as the report saw it."""
    email: str
    sent_at: str = ""
    bounced_at: str = ""
    bounce_code: str = ""
    opens: int = 0
    first_open: str = ""
    clicks: int = 0
    first_click: str = ""


@dataclass
class ReportResult:
    ok: bool = True
    error: str = ""
    recipients: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: list[str] = field(default_factory=list)
    left_for_later: int = 0
    completed: bool = False
    opens_recorded: bool = True

    def summary(self) -> dict[str, Any]:
        return {"ok": self.ok, "error": self.error, "recipients": self.recipients, "created": self.created,
                "updated": self.updated, "unchanged": self.unchanged, "unmatched": len(self.unmatched),
                "unmatchedAddresses": self.unmatched[:20], "leftForLater": self.left_for_later,
                "completed": self.completed, "opensRecorded": self.opens_recorded}

    def words(self) -> str:
        if not self.ok:
            return f"The send report could not be read: {self.error}"
        parts = [f"{self.recipients} recipient{'' if self.recipients == 1 else 's'} in the report",
                 f"{self.created} new", f"{self.updated} updated", f"{self.unchanged} unchanged"]
        text = ", ".join(parts) + "."
        if self.unmatched:
            text += (f" {len(self.unmatched)} address{'' if len(self.unmatched) == 1 else 'es'} matched no contact: "
                     + ", ".join(self.unmatched[:5]) + ("…" if len(self.unmatched) > 5 else "") + ".")
        if self.left_for_later:
            text += f" {self.left_for_later} more are written by the nightly pass."
        if not self.opens_recorded:
            text += " Opens are not recorded: this CRM has no place for them yet."
        if self.completed:
            text += " The reading window has closed, so the campaign is now Complete."
        return text


# --- the vendor ------------------------------------------------------------------------

async def primary_activity(mail, vendor_email_id: str) -> str:
    """The email's primary activity id, which the reports are keyed on."""
    detail = await mail.email_campaign(vendor_email_id)
    primary = next((a for a in detail.get("campaign_activities") or []
                    if str(a.get("role") or "") == "primary_email"), None)
    if not primary or not primary.get("campaign_activity_id"):
        raise ReportError("Constant Contact shows no sent email activity for the picked email.")
    return str(primary["campaign_activity_id"])


async def read_tracking(mail, activity_id: str) -> dict[str, list[dict[str, Any]]]:
    """Every tracking row, per kind."""
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in TRACKING_KINDS:
        rows: list[dict[str, Any]] = []
        async for item in mail._iter_pages(f"/reports/email_reports/{activity_id}/tracking/{kind}",
                                           {"limit": TRACKING_PAGE}, key="tracking_activities"):
            rows.append(item)
        out[kind] = rows
    return out


def _crm_time(value: Any) -> str:
    """The vendor's ISO time as the CRM's ``YYYY-MM-DD HH:MM:SS`` in UTC."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def summarise(tracking: dict[str, list[dict[str, Any]]]) -> dict[str, Recipient]:
    """One :class:`Recipient` per address (lower case), from every kind."""
    people: dict[str, Recipient] = {}

    def who(row: dict[str, Any]) -> Optional[Recipient]:
        email = str(row.get("email_address") or "").strip()
        if not email:
            return None
        return people.setdefault(email.lower(), Recipient(email=email))

    for row in tracking.get("sends") or []:
        r = who(row)
        if r:
            at = _crm_time(row.get("created_time"))
            if at and (not r.sent_at or at < r.sent_at):
                r.sent_at = at
    for row in tracking.get("bounces") or []:
        r = who(row)
        if r:
            r.bounced_at = r.bounced_at or _crm_time(row.get("created_time"))
            r.bounce_code = r.bounce_code or str(row.get("bounce_code") or "")
    for kind, count_attr, first_attr in (("opens", "opens", "first_open"), ("clicks", "clicks", "first_click")):
        for row in tracking.get(kind) or []:
            r = who(row)
            if not r:
                continue
            setattr(r, count_attr, getattr(r, count_attr) + 1)
            at = _crm_time(row.get("created_time"))
            if at and (not getattr(r, first_attr) or at < getattr(r, first_attr)):
                setattr(r, first_attr, at)
    return people


class ReportError(Exception):
    """A refusal or a vendor answer the report cannot use, in words."""


# --- matching ----------------------------------------------------------------------------

async def contacts_for(crm: EspoApi, addresses: list[str], *, from_list: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Address (lower case) → Contact id: the campaign's list first, then a
    Contact's own email, then a mentor profile's chapter address."""
    out: dict[str, str] = {a: cid for a, cid in (from_list or {}).items() if a in set(addresses)}
    left = [a for a in addresses if a not in out]
    for i in range(0, len(left), _ID_BATCH):
        chunk = left[i:i + _ID_BATCH]
        try:
            page = await crm.list(cfg.CONTACT, select="id,emailAddress", max_size=200,
                                  where=[{"type": "in", "attribute": "emailAddress", "value": chunk}])
        except EspoError as exc:
            log.warning("send report: contacts by email unreadable: %s", exc)
            break
        for c in page.get("list", []):
            out.setdefault(str(c.get("emailAddress") or "").lower(), c["id"])
    left = [a for a in addresses if a not in out]
    for i in range(0, len(left), _ID_BATCH):
        chunk = left[i:i + _ID_BATCH]
        try:
            page = await crm.list("CMentorProfile", select="id,cbmEmail,contactRecordId", max_size=200,
                                  where=[{"type": "in", "attribute": "cbmEmail", "value": chunk}])
        except EspoError as exc:
            log.warning("send report: chapter addresses unreadable: %s", exc)
            break
        for p in page.get("list", []):
            if p.get("contactRecordId"):
                out.setdefault(str(p.get("cbmEmail") or "").lower(), p["contactRecordId"])
    return out


async def list_addresses(crm: EspoApi, store, settings: Settings, campaign: dict[str, Any]) -> dict[str, str]:
    """The campaign's list resolved for email now: address → Contact id.
    Empty when there is no list (matching then falls back to the CRM)."""
    from . import audience

    try:
        chosen = await audience.audience_for_build(crm, store, settings, campaign)
    except Exception as exc:  # noqa: BLE001 — matching falls back to the CRM
        log.info("send report: the list of %s did not resolve: %s", campaign.get("id"), exc)
        return {}
    if not chosen:
        return {}
    return {str(t.get("email") or "").lower(): t["id"] for t in chosen["targets"] if t.get("email") and t.get("id")}


# --- writing the touches -------------------------------------------------------------------

async def open_fields_available(crm: EspoApi) -> bool:
    try:
        fields = await crm.metadata(f"entityDefs.{cfg.TOUCH}.fields") or {}
    except Exception:  # noqa: BLE001 — a probe never raises
        return False
    return isinstance(fields, dict) and all(isinstance(fields.get(f), dict) for f in OPEN_FIELDS)


def _same(a: Any, b: Any) -> bool:
    """Compare as a reader would: empty and None are equal, numbers as numbers."""
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return int(a or 0) == int(b or 0)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def wanted(r: Recipient, existing: Optional[dict[str, Any]], *, opens: bool, vendor_email_id: str) -> dict[str, Any]:
    """What the touch should hold for this recipient."""
    out: dict[str, Any] = {
        "touchStatus": cfg.TOUCH_RETURNED if r.bounced_at else cfg.TOUCH_DELIVERED,
        "sentAt": r.sent_at or (existing or {}).get("sentAt") or None,
        "returnedAt": r.bounced_at or None,
        "vendorPieceId": vendor_email_id[:64],
        "vendorStatus": (f"bounced: {r.bounce_code}" if r.bounce_code else "bounced") if r.bounced_at else "delivered",
        "clickCount": r.clicks,
        "firstClickedAt": r.first_click or None,
    }
    if opens:
        out.update(openCount=r.opens, firstOpenedAt=r.first_open or None)
    if r.clicks and not (existing or {}).get("outcome"):
        out["outcome"] = "Clicked"
    return out


async def apply_report(crm: EspoApi, campaign: dict[str, Any], people: dict[str, Recipient],
                       contact_of: dict[str, str], *, opens: bool, max_writes: Optional[int] = None) -> ReportResult:
    """One touch per matched recipient, created or updated in place."""
    result = ReportResult(recipients=len(people), opens_recorded=opens)
    vendor_id = str(campaign.get("vendorEmailId") or "")
    select = REPORT_SELECT_BASE + ("," + ",".join(OPEN_FIELDS) if opens else "")
    existing: dict[str, dict[str, Any]] = {}
    offset = 0
    while True:
        page = await crm.list(cfg.TOUCH, select=select, max_size=200, offset=offset, where=[
            {"type": "equals", "attribute": "outreachCampaignId", "value": campaign["id"]},
            {"type": "equals", "attribute": "channel", "value": cfg.KIND_EMAIL}])
        batch = page.get("list", [])
        for t in batch:
            if t.get("contactId") and t.get("touchStatus") != cfg.TOUCH_CANCELLED:
                existing.setdefault(t["contactId"], t)
        if len(batch) < 200:
            break
        offset += 200
    writes = 0
    for address, r in sorted(people.items()):
        contact_id = contact_of.get(address)
        if not contact_id:
            result.unmatched.append(r.email)
            continue
        if not r.sent_at and not r.bounced_at:
            continue  # opened or clicked with no send row: wait for the send to appear
        current = existing.get(contact_id)
        want = wanted(r, current, opens=opens, vendor_email_id=vendor_id)
        if current is not None:
            changes = {k: v for k, v in want.items() if not _same(current.get(k), v)}
            if not changes:
                result.unchanged += 1
                continue
        if max_writes is not None and writes >= max_writes:
            result.left_for_later += 1
            continue
        if current is None:
            await crm.create(cfg.TOUCH, {
                "name": f"{campaign.get('name') or 'Campaign'} — {r.email}"[:255], "channel": cfg.KIND_EMAIL,
                "outreachCampaignId": campaign["id"], "contactId": contact_id,
                **{k: v for k, v in want.items() if v is not None}})
            result.created += 1
        else:
            await crm.update(cfg.TOUCH, current["id"], changes)
            result.updated += 1
        writes += 1
    return result


# --- one campaign, and the worker's pass --------------------------------------------------

def _parse(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value or "")[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def window_closed(campaign: dict[str, Any], now: Optional[datetime] = None) -> bool:
    started = _parse(campaign.get("runStartedAt"))
    return bool(started and (now or datetime.now(timezone.utc)) - started > timedelta(days=REPORT_DAYS))


def refusal(settings: Settings) -> str:
    if not settings.campaign_send_report:
        return "The send report is switched off (Campaign send report at /setup)."
    if not (settings.campaign_list_sync and settings.campaign_lists):
        return "The send report needs Campaign lists and Campaign list copies switched on."
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        return "The mailing service is not connected here (System Settings, Mailing)."
    if settings.espo_dry_run:
        return "This deployment writes nothing to a CRM (dry run)."
    return ""


async def read_campaign(settings: Settings, campaign: dict[str, Any], *, crm: EspoApi, mail, store=None,
                        max_writes: Optional[int] = None, now: Optional[datetime] = None) -> ReportResult:
    """Read one campaign's report and write its touches. Completes the
    campaign once its reading window has closed. Never raises."""
    from core.mailing import MailingError

    if campaign.get("campaignKind") != cfg.KIND_EMAIL:
        return ReportResult(ok=False, error="This is not an email campaign.")
    if not campaign.get("vendorEmailId"):
        return ReportResult(ok=False, error="No email has been picked for this campaign yet (Pick the email).")
    try:
        activity = await primary_activity(mail, str(campaign["vendorEmailId"]))
        people = summarise(await read_tracking(mail, activity))
        from_list = await list_addresses(crm, store, settings, campaign) if store is not None else {}
        contact_of = await contacts_for(crm, sorted(people), from_list=from_list)
        result = await apply_report(crm, campaign, people, contact_of, opens=await open_fields_available(crm),
                                    max_writes=max_writes)
        if campaign.get("campaignStatus") == cfg.STATUS_RUNNING and window_closed(campaign, now) \
                and not result.left_for_later:
            await crm.update(cfg.CAMPAIGN, campaign["id"], {
                "campaignStatus": cfg.STATUS_COMPLETE,
                "runCompletedAt": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")})
            result.completed = True
        return result
    except (ReportError, MailingError, EspoError) as exc:
        return ReportResult(ok=False, error=str(exc))


async def run_report_cycle(settings: Settings, *, crm: Optional[EspoApi] = None, mail=None, conn_store=None,
                           campaign_store=None, now: Optional[datetime] = None) -> list[tuple[dict[str, Any], ReportResult]]:
    """The worker's pass: every Running email campaign with a picked email.
    Never raises."""
    if refusal(settings):
        return []
    try:
        from core.mailing_sync import _clients
        from .email import vendor_email_available
        crm, mail, conn_store = _clients(settings, crm, mail, conn_store)
        if not await vendor_email_available(crm):
            return []
        campaigns = await service._page_all(crm, cfg.CAMPAIGN, select=cfg.CAMPAIGN_SELECT + ",vendorEmailId", where=[
            {"type": "equals", "attribute": "campaignKind", "value": cfg.KIND_EMAIL},
            {"type": "equals", "attribute": "campaignStatus", "value": cfg.STATUS_RUNNING},
            {"type": "isNotNull", "attribute": "vendorEmailId"}], limit=1000)
    except Exception as exc:  # noqa: BLE001
        log.warning("send report pass: could not start: %s", exc)
        return []
    # The worker passes its own long-lived store; none means matching by the
    # CRM alone (never build a store here: one per pass leaks its pool).
    out = []
    for c in campaigns:
        result = await read_campaign(settings, c, crm=crm, mail=mail, store=campaign_store, now=now)
        log.info("send report %s: %s", c.get("id"), result.summary())
        out.append((c, result))
    return out
