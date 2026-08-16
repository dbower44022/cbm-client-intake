"""Guards for the event editor's shape.

The editor is browser code; what Python can usefully guard is the wiring that a
future edit could quietly undo — that the page loads the shared rich-text
editor, that the two long-form Content fields still go through it rather than
back to a raw textarea of HTML source, and that the modal keeps the pinned
Save/Cancel footer (a scrollbar must move content, never the buttons).
"""

from __future__ import annotations

from pathlib import Path

from events import config as cfg

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "events" / "frontend" / "index.html"
APP = ROOT / "events" / "frontend" / "app.js"
CSS = ROOT / "events" / "frontend" / "styles.css"


def test_the_page_loads_the_shared_rich_text_editor():
    html = PAGE.read_text()
    assert "/shared/vendor/jodit/jodit.min.css" in html
    assert "/shared/vendor/jodit/jodit.min.js" in html
    assert "/shared/richtext.js" in html
    # richtext.js wraps the vendor bundle, so the bundle must come first, and
    # both must precede the app that builds the Content panel from them.
    assert (
        html.index("jodit.min.js")
        < html.index("/shared/richtext.js")
        < html.index('src="app.js"')
    )


def test_long_form_content_fields_are_wysiwyg():
    """The website's event copy is written here, not hand-coded as HTML."""
    by_name = {f.name: f for f in cfg.EVENT_FIELDS}
    assert by_name["eventOverview"].type == "wysiwyg"
    assert by_name["eventSyllabus"].type == "wysiwyg"


def test_the_editor_renders_wysiwyg_through_cbmrichtext():
    source = APP.read_text()
    assert "window.CBMRichText" in source
    # And reads it back the same way — a getValue() that never happens is a
    # silently empty save.
    assert "_cbmRichText.getValue()" in source


def test_the_modal_keeps_save_and_cancel_out_of_the_scroll():
    """Only the body scrolls: the footer is a sibling with its own flex slot."""
    css = CSS.read_text()
    assert "resize: both" in css          # the card sizes to the user's screen
    assert ".ev__modal-body { flex: 1 1 auto; overflow: auto;" in css
    assert ".ev__modal-foot { flex: 0 0 auto;" in css


def test_form_controls_are_border_box():
    """The date+time control sizes its inputs in percentages; under content-box
    they overflowed their wrapper and collided with the Duration select."""
    css = CSS.read_text()
    assert "box-sizing: border-box" in css


def test_the_page_does_not_redefine_the_shared_button():
    """Buttons come from /shared/tokens.css, like every other staff tool."""
    css = CSS.read_text()
    for declaration in ("background: var(--cbm-gold", "background: #fff; color: var(--cbm-navy"):
        assert declaration not in css
