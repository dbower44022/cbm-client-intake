"""Guards for the Overview tab's shape: the whole record, read-only.

Doug's rule (2026-09-16): the view screen shows ALL the data about an event so
a person can check it without opening the editor — facts on the left, the
website-facing content (graphic, Summary, Full description, Syllabus) on the
right. The renderer is browser code; what Python can guard is the wiring a
future edit could quietly undo.
"""

from __future__ import annotations

import re
from pathlib import Path

from events import config as cfg

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "events" / "frontend" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "events" / "frontend" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "events" / "frontend" / "styles.css").read_text(encoding="utf-8")


def _overview_panel() -> str:
    start = PAGE.index('data-panel="overview"')
    end = PAGE.index('data-panel="registrants"')
    return PAGE[start:end]


def test_the_overview_has_a_facts_column_and_a_content_column():
    panel = _overview_panel()
    assert 'class="ev__overview-facts"' in panel
    assert 'class="ev__overview-content"' in panel
    # Facts first in source order, so the content column is on the RIGHT.
    assert panel.index("ev__overview-facts") < panel.index("ev__overview-content")


def test_the_content_column_carries_graphic_summary_description_and_syllabus():
    panel = _overview_panel()
    content = panel[panel.index("ev__overview-content"):]
    for element_id in (
        "overviewGraphic", "overviewSummary", "overviewDescription", "overviewSyllabus",
    ):
        assert f'id="{element_id}"' in content, element_id
    # In the order the website presents them.
    assert (
        content.index("overviewGraphic")
        < content.index("overviewSummary")
        < content.index("overviewDescription")
        < content.index("overviewSyllabus")
    )


def test_every_content_slot_renders_even_when_empty():
    """A slot that vanishes reads as a missing feature. The figure is never
    hidden — only its <img> — and the rich-text hosts fall back to a dash."""
    panel = _overview_panel()
    assert 'id="overviewGraphicWrap" hidden' not in panel
    assert 'id="overviewGraphic" alt="" hidden' in panel
    assert 'id="overviewGraphicEmpty"' in panel
    assert 'if (empty) { host.textContent = "—"; return; }' in APP
    assert '$("overviewSummary").textContent = event.summary || "—";' in APP


def test_rich_text_is_rendered_through_the_shared_sanitizer():
    """The description and syllabus are HTML authored in the CRM, rendered as
    HTML the way the website does — but staff-authored is not trusted, so it
    goes through the same sanitizer every editor uses."""
    assert "window.CBMRichText.sanitizeHtml(html || \"\")" in APP
    assert 'setRich($("overviewDescription"), event.overview);' in APP
    assert 'setRich($("overviewSyllabus"), event.syllabus);' in APP


def test_the_facts_are_driven_by_the_editor_field_spec():
    """One spec serves the editor AND the overview, so a field added to
    EVENT_FIELDS shows on the view screen without a second edit."""
    assert "state.fields.forEach(function (spec) {" in APP
    assert "factRow(host, spec.label, factValue(spec, raw, event));" in APP
    # Every type the spec uses has a formatting case.
    types_in_spec = {f.type for f in cfg.EVENT_FIELDS}
    cases = set(re.findall(r'case "([a-z]+)":', APP[APP.index("function factValue"):]))
    # wysiwyg is the content column, not a fact; the three plain kinds share the default.
    assert types_in_spec - {"varchar", "text", "enum", "wysiwyg"} <= cases, types_in_spec - cases


def test_the_record_read_carries_every_spec_field():
    """The overview can only show what the read selects. `duration` is virtual
    (derived from the two dates) and the graphic rides as its attachment id."""
    selected = set(cfg.PUBLIC_SELECT.split(","))
    for field in cfg.EVENT_FIELDS:
        name = field.name
        if name == "duration":
            continue
        if name == "eventGraphic":
            name = "eventGraphicId"
        assert name in selected, name


def test_the_graphic_is_served_through_the_staff_proxy():
    """So it shows for an unpublished event — the public route is gated."""
    assert '"/graphic?v=" + encodeURIComponent(graphicId)' in APP


def test_the_two_columns_are_a_grid_that_stacks_when_narrow():
    assert ".ev__overview { display: grid;" in CSS
    # display:grid beats [hidden]; the guard must be repeated at this specificity.
    assert ".ev__overview[hidden] { display: none !important; }" in CSS
    assert "max-width" not in CSS[CSS.index(".ev__overview {"):CSS.index(".ev__overview[hidden]")]
    assert ".ev__overview { grid-template-columns: minmax(0, 1fr); }" in CSS
