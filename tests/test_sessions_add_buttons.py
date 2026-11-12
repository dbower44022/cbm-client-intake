"""Client Management's Details tab names what each add button adds, and its
CBM Contacts button opens the co-mentor picker directly (Doug's request
11-11-26, OPEN-ITEMS #78). A static check of the shared session frontend."""
from pathlib import Path

APP_JS = (Path(__file__).resolve().parent.parent / "sessions" / "frontend" / "app.js").read_text()


def test_engagement_add_buttons_are_named():
    assert '"Add Client Contacts"' in APP_JS
    assert '"Add Co-Mentors"' in APP_JS


def test_co_mentor_button_skips_the_menu():
    # The CBM button's open state is the picker itself, not the one-item menu.
    assert 'if (engagement && side === "cbm") menuKey = "cbm-pick";' in APP_JS


def test_other_domains_keep_plus_add():
    assert 'btn.textContent = "+ Add";' in APP_JS
    assert 'var engagement = SLUG === "mentorsessions";' in APP_JS
