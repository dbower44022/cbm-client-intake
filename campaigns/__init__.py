"""Campaign Management — prospect marketing, Phase 1.

The arc lives in ``prds/prospect-marketing/`` (``README.md`` first, then
``rulings.md`` and ``build-plan.md``). This package is § 3's shared engine:
``config.py`` (the CRM names and the field whitelists), ``service.py`` (the CRM
logic), ``router.py`` (the staff API, team-gated, every mutation action-logged),
``public.py`` (the link resolve ``/c/{token}``, the public name lookup, the QR
images), ``landing.py`` (the postcard landing page ``/p/{token}``, § 4),
``imports.py`` (the state-filing import, § 2), ``postcard.py`` (the postcard run
the worker executes, § 3.2), ``store.py`` (the links and the import ledger in
the application database — ruling 31) and ``frontend/``.

Dark behind ``CAMPAIGNS_ENABLED``, read per request. Every CRM-facing read
feature-detects its entity or link from metadata, so a CRM without the Phase 1
change (production until its Sunday slot) stays dark with a logged note.
"""
