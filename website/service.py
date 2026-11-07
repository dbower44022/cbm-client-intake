"""What ``GET /api/website/settings`` answers (Association rulings 32 and 45).

The shape is the prototype stand-in's (``chapter-website-prototype/mock-apps``),
which the chapter connector already reads. Rules kept here:

* **The contract version** goes up only when a field changes meaning or is
  removed. New fields are added without a change, and the chapter connector
  ignores fields it does not know (WT-27: chapters run different releases).
* **A value that fails its check is left out**, never passed on. The save path
  refuses a bad value, but the deployment's own configuration is not checked
  there, and the website must not receive a broken colour or address.
* **A key page reads off unless this release can serve it**, whatever is
  stored (WT-10, WT-22): a menu entry must never lead to "page not found".
"""

from __future__ import annotations

from typing import Any, Optional

from core.config import Settings
from core.settings_registry import (
    WEBSITE_PAGE_SWITCHES,
    WEBSITE_PAGES_SERVED,
    website_value_problem,
)

CONTRACT_VERSION = 1

COLOR_SLUGS: dict[str, str] = {
    "base": "website_color_base",
    "contrast": "website_color_contrast",
    "accent-1": "website_color_accent_1",
    "accent-2": "website_color_accent_2",
    "accent-3": "website_color_accent_3",
    "accent-4": "website_color_accent_4",
    "accent-5": "website_color_accent_5",
    "accent-6": "website_color_accent_6",
}


def _clean(settings: Settings, key: str) -> str:
    value = str(getattr(settings, key, "") or "").strip()
    return "" if website_value_problem(key, value) else value


def _social(settings: Settings) -> list[dict[str, str]]:
    if website_value_problem("chapter_social_links", settings.chapter_social_links or ""):
        return []
    out = []
    for pair in (settings.chapter_social_links or "").split(","):
        label, _, url = pair.strip().partition("|")
        if label.strip() and url.strip():
            out.append({"label": label.strip(), "url": url.strip()})
    return out


def image_url(base: str, name: str, meta: Optional[dict[str, Any]]) -> str:
    """The image's public address, carrying its fingerprint so a replaced
    image is fetched afresh rather than served from a cache."""
    if not meta:
        return ""
    return f"{base}/api/website/images/{name}?v={meta['sha256'][:12]}"


def settings_payload(settings: Settings, images: dict[str, dict[str, Any]], base: str) -> dict[str, Any]:
    """The Website group as the chapter connector reads it. ``base`` is the
    applications' public address, without a trailing slash."""
    base = base.rstrip("/")
    logo = image_url(base, "logo", images.get("logo"))
    if not logo:
        fallback = (settings.organization_logo_url or "").strip()
        logo = fallback if fallback.startswith("https://") else ""
    return {
        "version": CONTRACT_VERSION,
        "colors": {slug: v for slug, key in COLOR_SLUGS.items() if (v := _clean(settings, key))},
        "fonts": {k: v for k, v in (("heading", _clean(settings, "website_font_heading")),
                                    ("body", _clean(settings, "website_font_body"))) if v},
        "logoUrl": logo or None,
        "headerImage": image_url(base, "header", images.get("header")) or None,
        "chapter": {
            "name": (settings.organization_name or "").strip(),
            "abbreviation": (settings.organization_abbreviation or "").strip(),
            "email": _clean(settings, "chapter_email"),
            "phone": (settings.chapter_phone or "").strip(),
            "address": (settings.chapter_postal_address or "").strip(),
            "ein": _clean(settings, "chapter_ein"),
            "paymentLink": _clean(settings, "chapter_payment_url"),
            "social": _social(settings),
        },
        "pages": {
            page: bool(getattr(settings, key, False)) and page in WEBSITE_PAGES_SERVED
            for page, key in WEBSITE_PAGE_SWITCHES.items()
        },
    }
