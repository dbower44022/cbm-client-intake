"""CRM side of the Communications pipeline.

Enumerates the mailboxes to sync (managers = ``CMentorProfile`` with a linked
login User and a ``cbmEmail``) and the ACTIVE records each one owns, with each
record's contact email addresses — the scope that bounds what mail is ever
fetched or stored (plan §5.1). Also owns the ``CConversation`` /
``CCommunication`` entity vocabulary and the upsert/link helpers the sync uses.

All reads/writes here run as the intake API user (like the submission
pipeline); the entities' grants are specified in ``cconversation-entity.md``.
Record volumes are CBM-scale (tens), so the per-record related reads are fine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from assignments.service import assigned_user_id
from core.espo import EspoError

log = logging.getLogger("cbm_intake.comms.crm")

CONVERSATION = "CConversation"
COMMUNICATION = "CCommunication"
MENTOR_PROFILE = "CMentorProfile"

# CConversation linkMultiple link per parent entity (read via list_related,
# written via relate/unrelate — [[espo-custom-linkmultiple-is-a-relationship]]).
PARENT_LINKS = {
    "CEngagement": "engagements",
    "CPartnerProfile": "partnerProfiles",
    "CSponsorProfile": "sponsorProfiles",
}
# Link on CConversation for a parent record's Contacts.
CONTACTS_LINK = "contacts"
# hasMany from conversation to its messages; the FK on CCommunication.
MESSAGES_LINK = "communications"
CONVERSATION_FK = "conversationId"

_PAGE = 200


@dataclass
class RecordRef:
    """One active record in a mailbox's scope."""

    entity: str  # CEngagement | CPartnerProfile | CSponsorProfile
    id: str
    name: str
    contact_ids: set[str] = field(default_factory=set)
    addresses: set[str] = field(default_factory=set)  # lowercased contact emails
    # address -> Contact id, for parenting the Email write-back to a recipient
    # (only populated by the targeted single-record build, not the sync sweep).
    contact_by_address: dict[str, str] = field(default_factory=dict)


@dataclass
class MailboxScope:
    """Everything the sync needs for one manager's mailbox."""

    mailbox: str  # the manager's @cbmentors.org address
    manager_name: str
    owner_user_id: Optional[str]  # their login User (for owner-stamping)
    records: list[RecordRef] = field(default_factory=list)
    # Internal email domains: a message whose EVERY participant is at one of
    # these is internal chatter, not client correspondence — the sweep skips
    # it (see ingest_message). Left empty by the explicit-action scopes
    # (record-page compose write-through, thread include) so a deliberate
    # internal send still shows on its record.
    internal_domains: set[str] = field(default_factory=set)

    @property
    def all_addresses(self) -> set[str]:
        out: set[str] = set()
        for rec in self.records:
            out |= rec.addresses
        return out

    def records_for(self, addresses: set[str]) -> list[RecordRef]:
        """The records whose contacts include any of ``addresses``."""
        return [r for r in self.records if r.addresses & addresses]


# Per-domain: (profile reverse link, contacts link, status attr, mode)
# mode "include" keeps only the listed statuses; "exclude" drops them;
# "all" takes everything. Status lists come from Settings (plan §5.1).
_DOMAINS = (
    ("CEngagement", "engagements1", "engagementContacts", "engagementStatus", "include"),
    ("CPartnerProfile", "managedPartners", "contacts", "partnershipStatus", "exclude"),
    ("CSponsorProfile", "managedSponsors", "sponsorContacts", None, "all"),
)


def _contact_addresses(contact: dict[str, Any]) -> set[str]:
    """A contact's addresses (primary + any secondary in emailAddressData)."""
    out = set()
    if contact.get("emailAddress"):
        out.add(str(contact["emailAddress"]).strip().lower())
    for entry in contact.get("emailAddressData") or []:
        addr = (entry or {}).get("emailAddress")
        if addr:
            out.add(str(addr).strip().lower())
    return out


async def build_scopes(client: Any, settings: Any) -> list[MailboxScope]:
    """One :class:`MailboxScope` per manager with a CBM mailbox + active records."""
    data = await client.list(
        MENTOR_PROFILE,
        select="name,cbmEmail,assignedUserId,assignedUsersIds",
        max_size=_PAGE,
    )
    include_eng = set(settings.comms_engagement_statuses_list)
    exclude_partner = set(settings.comms_partner_excluded_statuses_list)
    internal = set(settings.comms_internal_domains_list)

    scopes: list[MailboxScope] = []
    for profile in data.get("list", []):
        mailbox = (profile.get("cbmEmail") or "").strip().lower()
        owner = assigned_user_id(profile)
        if not mailbox or not owner:
            continue  # no mailbox to read, or no login user to own the records
        scope = MailboxScope(
            mailbox=mailbox,
            manager_name=profile.get("name") or "",
            owner_user_id=owner,
            internal_domains=internal,
        )
        for entity, reverse_link, contacts_link, status_attr, mode in _DOMAINS:
            try:
                related = await client.list_related(
                    MENTOR_PROFILE, profile["id"], reverse_link,
                    select=f"name,{status_attr}" if status_attr else "name",
                    max_size=_PAGE,
                )
            except EspoError as exc:
                log.warning("scope: %s/%s unreadable: %s", mailbox, reverse_link, exc)
                continue
            for rec in related.get("list", []):
                status = rec.get(status_attr) if status_attr else None
                if mode == "include" and status not in include_eng:
                    continue
                if mode == "exclude" and status in exclude_partner:
                    continue
                ref = RecordRef(entity=entity, id=rec["id"], name=rec.get("name") or "")
                try:
                    contacts = await client.list_related(
                        entity, rec["id"], contacts_link,
                        select="name,emailAddress", max_size=_PAGE,
                    )
                except EspoError as exc:
                    log.warning("scope: %s/%s contacts unreadable: %s", entity, rec["id"], exc)
                    contacts = {}
                for c in contacts.get("list", []) or []:
                    ref.contact_ids.add(c["id"])
                    # Internal (staff) addresses never define the match scope:
                    # a mentor's own Contact linked to an engagement would
                    # otherwise sweep ALL internal mail with that mentor into
                    # the CRM (the cbmentor↔cbmentor noise, 2026-07-21).
                    ref.addresses |= {
                        a
                        for a in _contact_addresses(c)
                        if a.rsplit("@", 1)[-1] not in internal
                    }
                if ref.addresses:
                    scope.records.append(ref)
        if scope.records:
            scopes.append(scope)
    return scopes


# --- conversation / communication persistence --------------------------------


async def find_communication_by_rfc_id(client: Any, rfc_id: str) -> Optional[dict[str, Any]]:
    return await client.find_one(
        COMMUNICATION, "rfcMessageId", rfc_id, select=f"id,{CONVERSATION_FK}"
    )


async def find_conversation_for_thread(
    client: Any, mailbox: str, thread_id: str
) -> Optional[str]:
    """A conversation already holding messages of this Gmail thread (per mailbox)."""
    data = await client.list(
        COMMUNICATION,
        where=[
            {"type": "equals", "attribute": "gmailThreadId", "value": thread_id},
            {"type": "equals", "attribute": "sourceMailbox", "value": mailbox},
        ],
        select=CONVERSATION_FK,
        max_size=1,
    )
    rows = data.get("list", [])
    return rows[0].get(CONVERSATION_FK) if rows else None


async def find_conversation_by_refs(client: Any, ref_ids: list[str]) -> Optional[str]:
    """Cross-mailbox merge: a referenced RFC Message-ID already stored anywhere
    (e.g. the co-mentor's copy) puts this message in that conversation."""
    for rid in ref_ids[:5]:
        row = await find_communication_by_rfc_id(client, rid)
        if row and row.get(CONVERSATION_FK):
            return row[CONVERSATION_FK]
    return None


async def create_conversation(client: Any, *, subject: str, sent_at: str) -> str:
    created = await client.create(
        CONVERSATION,
        {
            "name": (subject or "(no subject)")[:250],
            "conversationStatus": "Open",
            "firstMessageAt": sent_at or None,
            "lastMessageAt": sent_at or None,
            "messageCount": 0,
        },
    )
    return created["id"]


PARTICIPANTS_MAX = 500  # the CRM field's varchar length


def _clean_name(name: str) -> str:
    """A display name safe for the flat comma-separated participants field."""
    return " ".join((name or "").replace(",", " ").replace("<", " ").replace(">", " ").split())


def _participant_key(entry: str) -> str:
    """Dedup key for a stored entry: the email address when one is present,
    else the (legacy, name-only) text itself."""
    if "<" in entry and entry.endswith(">"):
        addr = entry[entry.rindex("<") + 1 : -1].strip().lower()
        if addr:
            return addr
    if "@" in entry and " " not in entry:
        return entry.lower()
    return "name:" + entry.lower()


def participants_contain(existing: str, address: str) -> bool:
    """True when the stored participants display string contains ``address``
    (case-insensitive), using the same entry parser the merge uses. Legacy
    name-only entries (pre-v0.55.0 senders-only format) never match an
    address — callers filtering "my conversations" accept that gap."""
    addr = (address or "").strip().lower()
    if not addr:
        return False
    for token in (existing or "").split(","):
        token = token.strip()
        if token and _participant_key(token) == addr:
            return True
    return False


def merge_participants(existing: str, additions: Iterable[tuple[str, str]]) -> str:
    """Fold ``(display name, address)`` pairs into the participants display
    string, deduping by email address so the same person never appears twice.

    Entries are stored as ``Name <address>`` (bare address when no name is
    known). A bare-address entry is upgraded in place once a later message
    supplies the display name; a legacy name-only entry (the pre-v0.55.0
    senders-only format) is upgraded once its address is learned. Existing
    entry order is preserved; the result is clamped to whole entries within
    the CRM field length.
    """
    order: list[str] = []
    by_key: dict[str, str] = {}
    for token in (existing or "").split(","):
        token = token.strip()
        if not token:
            continue
        key = _participant_key(token)
        if key not in by_key:
            order.append(key)
            by_key[key] = token
    for name, address in additions:
        addr = (address or "").strip().lower()
        clean = _clean_name(name)
        entry = f"{clean} <{addr}>" if clean and addr else (addr or clean)
        if not entry:
            continue
        key = addr or ("name:" + clean.lower())
        legacy = "name:" + clean.lower() if (addr and clean) else ""
        if key in by_key:
            if addr and clean and "<" not in by_key[key]:
                by_key[key] = entry  # bare address → named form
            # The same person may also sit in the list as a legacy name-only
            # entry (address learned bare-first, name later) — drop it.
            if legacy and legacy in by_key:
                order.remove(legacy)
                del by_key[legacy]
            continue
        if legacy and legacy in by_key:
            order[order.index(legacy)] = key
            del by_key[legacy]
            by_key[key] = entry
            continue
        order.append(key)
        by_key[key] = entry
    out: list[str] = []
    used = 0
    for key in order:
        token = by_key[key]
        extra = len(token) + (2 if out else 0)
        if used + extra > PARTICIPANTS_MAX:
            break
        out.append(token)
        used += extra
    return ", ".join(out)


async def refresh_participants(
    client: Any, conversation_id: str, participants: Iterable[tuple[str, str]]
) -> None:
    """Fold participants into an EXISTING conversation without touching the
    counters/stamps — the dedup/replay path (an already-stored message seen
    again, e.g. a GMAIL_RESYNC pass), which is how pre-v0.55.0 senders-only
    conversations backfill their recipients. Best-effort."""
    try:
        conv = await client.get(CONVERSATION, conversation_id, select="participants")
        current = (conv.get("participants") or "").strip()
        merged = merge_participants(current, participants)
        if merged and merged != current:
            await client.update(CONVERSATION, conversation_id, {"participants": merged})
    except EspoError as exc:
        log.warning("conversation %s participants update failed: %s", conversation_id, exc)


async def refresh_conversation_aggregates(
    client: Any, conversation_id: str, *, sent_at: str,
    participants: Iterable[tuple[str, str]],
) -> None:
    """Bump counters/stamps after a new message and fold everyone on it
    (From/To/Cc, as (name, address) pairs) into the participants list; null
    summarizedAt so the optional AI layer re-summarizes. Best-effort."""
    try:
        conv = await client.get(
            CONVERSATION, conversation_id,
            select="messageCount,firstMessageAt,lastMessageAt,participants",
        )
        payload: dict[str, Any] = {
            "messageCount": int(conv.get("messageCount") or 0) + 1,
            "summarizedAt": None,
        }
        if sent_at:
            if not conv.get("firstMessageAt") or sent_at < conv["firstMessageAt"]:
                payload["firstMessageAt"] = sent_at
            if not conv.get("lastMessageAt") or sent_at > conv["lastMessageAt"]:
                payload["lastMessageAt"] = sent_at
        merged = merge_participants(conv.get("participants") or "", participants)
        if merged and merged != (conv.get("participants") or "").strip():
            payload["participants"] = merged
        await client.update(CONVERSATION, conversation_id, payload)
    except EspoError as exc:
        log.warning("conversation %s aggregate update failed: %s", conversation_id, exc)


async def link_records(
    client: Any,
    conversation_id: str,
    records: list[RecordRef],
    excludes: set[tuple[str, str, str]],
) -> None:
    """Relate the conversation to each matched record (+ its matched contacts),
    honoring exclusions. Relates are idempotent; failures are logged, not fatal."""
    for rec in records:
        if (rec.entity, rec.id, conversation_id) in excludes:
            continue
        link = PARENT_LINKS.get(rec.entity)
        if not link and rec.entity != "Contact":
            continue
        if link:
            try:
                await client.relate(CONVERSATION, conversation_id, link, rec.id)
            except EspoError as exc:
                log.warning(
                    "link %s->%s/%s failed: %s", conversation_id, rec.entity, rec.id, exc
                )
        for cid in rec.contact_ids:
            # A contact-level exclude (a View Contact page "Remove") must hold
            # against re-linking, whichever record scope matched the contact.
            if ("Contact", cid, conversation_id) in excludes:
                continue
            try:
                await client.relate(CONVERSATION, conversation_id, CONTACTS_LINK, cid)
            except EspoError as exc:
                # The record link above is what matters, but a silently missing
                # contact link still surprises in the CRM UI — log it.
                log.warning(
                    "contact link %s -> Contact/%s failed: %s",
                    conversation_id, cid, exc,
                )


async def stamp_owners(client: Any, conversation_id: str, owner_ids: set[str]) -> None:
    """Merge the owning managers into assignedUsers so read-own roles can see
    the conversation (the CSession owner-stamp pattern). Best-effort."""
    if not owner_ids:
        return
    try:
        conv = await client.get(CONVERSATION, conversation_id, select="assignedUsersIds")
        current = set(conv.get("assignedUsersIds") or [])
        merged = current | owner_ids
        if merged != current:
            await client.update(
                CONVERSATION, conversation_id, {"assignedUsersIds": sorted(merged)}
            )
    except EspoError as exc:
        log.warning("owner stamp on %s failed: %s", conversation_id, exc)
