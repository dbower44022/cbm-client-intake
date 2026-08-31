"""Inline images for the wysiwyg editors — the one shared engine.

The RIGHT way to keep an image a user pastes, drops or picks into a rich-text
field (established in the session tools, 2026-07-24): store it as an EspoCRM
Attachment with role "Inline Attachment", referenced from the wysiwyg HTML as
``<img src="?entryPoint=attachment&amp;id=…">`` — exactly what EspoCRM's own
editor stores. EspoCRM's Wysiwyg saver then binds the attachment to the record
when the field is saved (so cleanup never collects it, its ACL follows the
record, and the CRM UI renders it too), and the app proxies the bytes for
display because the browser cannot reach the CRM.

That binding is the reason uploads are only accepted for fields whose live CRM
type is ``wysiwyg`` — an attachment referenced from a plain-``text`` field is
never bound, so EspoCRM's cleanup job would silently collect it later. Callers
pass the field whitelist (their own spec) and this module holds the shared
validation, naming and size rules.
"""

from __future__ import annotations

import logging
from typing import Collection

log = logging.getLogger(__name__)


class InlineImageError(ValueError):
    """A readable validation refusal — routers map it to a 400."""


INLINE_IMAGE_MAX_MB = 5
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# EspoCRM validates an inline attachment by deriving the mime type FROM THE
# FILENAME EXTENSION and requiring it to equal the declared type
# (Tools/Attachment/Checker.php checkTypeImage) — an extensionless name is
# rejected with "Not allowed file type." (found live 2026-07-24), so the
# stored filename always carries the canonical extension for its type.
_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def attachment_name(filename: str, content_type: str) -> str:
    """A filename EspoCRM's attachment checker accepts for ``content_type``.

    Exact lowercase extension required (".jpeg" also maps to image/jpeg);
    anything else — missing, wrong, or upper-case — is rebuilt on the stem.
    """
    ext = _EXT[content_type]
    name = (filename or "pasted-image").strip() or "pasted-image"
    if not name.endswith(ext) and not (ext == ".jpg" and name.endswith(".jpeg")):
        name = name.rsplit(".", 1)[0] if "." in name else name
        name = (name or "pasted-image") + ext
    return name


async def upload_inline_image(
    client,
    *,
    filename: str,
    content_type: str,
    data_base64: str,
    related_type: str,
    field: str,
    allowed_fields: Collection[str],
    field_error: str = "Images can only be added to the rich-text fields.",
    too_large_hint: str = "",
) -> dict[str, str]:
    """Store an image as an EspoCRM Inline Attachment and return its id.

    Validation refusals raise :class:`InlineImageError` with a message fit to
    show the user; the caller's router maps it to a readable 400.
    """
    if field not in allowed_fields:
        raise InlineImageError(field_error)
    if content_type not in ALLOWED_TYPES:
        raise InlineImageError(
            "Only JPEG, PNG, WebP, or GIF images can be used here."
        )
    # base64 is ~4/3 of the decoded size; cap before any decode/transfer.
    if len(data_base64) * 3 // 4 > INLINE_IMAGE_MAX_MB * 1024 * 1024:
        raise InlineImageError(
            f"The image is too large (limit {INLINE_IMAGE_MAX_MB} MB)."
            + (" " + too_large_hint if too_large_hint else "")
        )
    attachment_id = await client.upload_attachment(
        filename=attachment_name(filename, content_type),
        content_type=content_type,
        data_base64=data_base64,
        related_type=related_type,
        field=field,
        role="Inline Attachment",
    )
    log.info(
        "inline image stored as Attachment/%s (%s.%s, %s, ~%d KB)",
        attachment_id, related_type, field, content_type,
        len(data_base64) * 3 // 4 // 1024,
    )
    return {"id": attachment_id}


async def fetch_inline_image(client, attachment_id: str) -> tuple[bytes, str]:
    """The attachment's bytes + content type, read AS THE CALLER'S CLIENT —
    when that is the signed-in user, EspoCRM checks access against the related
    record, so a viewer sees an image iff they can read the record it belongs
    to."""
    return await client.download_attachment(attachment_id)
