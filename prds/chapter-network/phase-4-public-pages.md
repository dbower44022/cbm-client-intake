# Phase 4 — Public pages (ruling 8)

**Status: not started here.** Its substance lives in
`prds/public-mentor-pages-plan.md`, which this phase promotes from a Cleveland
nicety to a **network-level prerequisite**.

---

## Branding, and the public pages (ruling 8)

Two places in the app deliberately reproduce Cleveland's website byte-for-byte:
`mentorprofile/frontend/` carries the site's Elementor HTML and CSS verbatim so a
mentor's preview is an exact reproduction of their public page, and
`wp-plugin/cbm-events/cbm-events.css` is copied from the live page's widgets —
that one only in v0.203.0, precisely because an approximation had been hiding a
real class-contract defect for three weeks. Both are coupled to **one specific
website**, and neither is reachable by ruling 4, because neither is CRM
configuration. Six chapters would mean six verbatim copies chasing six
independently-redesigned WordPress sites.

Ruling 8 ends this rather than multiplying it. **`prds/public-mentor-pages-plan.md`
is therefore a network-level prerequisite, not a Cleveland nicety.** Its embed
mechanics become load-bearing for every chapter: the `frame-ancestors` header (per
chapter, naming that chapter's site), height sync to the parent, and deep-link
sync so a mentor inside the frame is shareable. The same shape covers the events
programme, which `wp-plugin/cbm-events/` already almost delivers — it ships the
renderer plus the stylesheet and is one step from a distributable chapter plugin
configured with that chapter's app URL and `eventUrlBase`.

Per-chapter visual identity is then `tokens.css` overrides plus a logo — a small,
contained, versioned asset set, not a copy of anybody's site.

**De-Clevelanding is an explicit workstream** — measured in full in
[Phase 0](phase-0-decleveland.md). In outline: the settings are cheap and already
settings, the markup is the work (18 frontend HTML files, 48 occurrences), and there are four surfaces
outside HTML that the first pass missed, including one that hands a chapter's
applicants Cleveland's own privacy policy.


---

## What this phase must not break

Both of the byte-copies named above are byte-copies **on purpose**, and the
[Phase 0](phase-0-decleveland.md) § 8 ruling to leave them alone stands until this
phase actually retires them — parameterizing a verbatim copy fights the thing that
makes it correct. `wp-plugin/cbm-events/assets/cbm-events.css` is additionally a
**class contract** with the live site, guarded by a test, because a drift there
went unnoticed for three weeks.
