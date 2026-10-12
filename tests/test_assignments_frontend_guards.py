"""Static guards for the Client Administration frontend.

A bare ``display: flex`` on an element toggled with the ``hidden`` attribute
beats the attribute — the edit-mode Cancel/Save pair showed in VIEW mode from
v0.210.0 until Doug's screenshot on 2026-10-12, where Cancel had nothing to
cancel. Every toggled container in this stylesheet must gate its display on
``:not([hidden])``.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "assignments" / "frontend" / "styles.css").read_text()
HTML = (ROOT / "assignments" / "frontend" / "index.html").read_text()
JS = (ROOT / "assignments" / "frontend" / "app.js").read_text()

# Classes the page toggles with the hidden attribute (markup or script).
TOGGLED = ("modal__footactions", "modal", "modal__referral", "edit-form")


def _display_rules(cls: str) -> list[str]:
    """Every selector block that sets ``display`` for ``.cls``."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        sel, body = m.group(1).strip(), m.group(2)
        if re.search(rf"\.{re.escape(cls)}(?![\w-])", sel) and re.search(r"display\s*:\s*(?!none)", body):
            out.append(sel)
    return out


def test_toggled_containers_gate_display_on_not_hidden():
    for cls in TOGGLED:
        for sel in _display_rules(cls):
            assert ":not([hidden])" in sel, f".{cls} sets display without :not([hidden]): {sel}"


def test_the_footer_actions_are_toggled_by_the_script():
    assert 'modalViewActions").hidden' in JS and 'modalEditActions").hidden' in JS
    assert 'id="modalEditActions" hidden' in HTML
