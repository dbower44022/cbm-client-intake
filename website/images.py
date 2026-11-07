"""The two Website images — the logo and the header graphic — checked before
they are stored (plan decision 4.3).

The type is read from the file's own first bytes, never from what the browser
claims. SVG is refused: an SVG can carry script, and these files are served
from the applications' own address, where a script would run with the staff
pages' privileges.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Optional

#: The two images, by the name used in their addresses.
IMAGE_NAMES: dict[str, str] = {"logo": "Logo", "header": "Header graphic"}

MAX_BYTES = 2 * 1024 * 1024

_DATA_URI = re.compile(r"^data:[^;,]*;base64,", re.IGNORECASE)


class ImageError(ValueError):
    """An upload that cannot be stored, in words an administrator can act on."""


def sniff(data: bytes) -> Optional[str]:
    """The content type the bytes really are, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode(payload: str) -> tuple[bytes, str]:
    """Bytes and content type from a base64 string or a ``data:`` address.

    Raises :class:`ImageError` naming what is wrong."""
    raw = _DATA_URI.sub("", (payload or "").strip(), count=1)
    if not raw:
        raise ImageError("No image was sent.")
    # base64 is a third larger than the file; refuse before decoding a huge one.
    if len(raw) > (MAX_BYTES * 4) // 3 + 8:
        raise ImageError("The image is larger than 2 MB. Save it smaller and try again.")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("The upload was not a readable image file.") from exc
    if len(data) > MAX_BYTES:
        raise ImageError("The image is larger than 2 MB. Save it smaller and try again.")
    head = data[:512].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg"):
        raise ImageError(
            "SVG images are not accepted, because an SVG file can carry a script. "
            "Save it as PNG and upload that.")
    kind = sniff(data)
    if kind is None:
        raise ImageError("Only PNG, JPEG and WebP images are accepted.")
    return data, kind
