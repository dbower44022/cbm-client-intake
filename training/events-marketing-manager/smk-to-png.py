"""Turn Snagit/pmockit ``.smk`` captures into the PNG files the course needs.

A ``.smk`` is a zip holding ``items.json``, whose first item carries the
full-resolution image as base64 PNG in ``image_data``. A browser cannot render
a ``.smk``, so every capture saved in that format has to become a ``.png``
beside it before the course can show it.

Run it with no arguments after saving captures:

    uv run python \\
      /home/doug/Dropbox/Projects/cbm-client-intake/training/events-marketing-manager/smk-to-png.py

It writes only PNGs that are missing or older than their ``.smk``; pass
``--force`` to rewrite them all. The ``.smk`` files are git-ignored working
files, the PNGs are what the course publishes.
"""

from __future__ import annotations

import argparse
import base64
import json
import struct
import zipfile
from pathlib import Path

SHOTS = Path(__file__).resolve().parent / "course" / "shots"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def image_from_smk(path: Path) -> bytes:
    """Return the full-resolution PNG bytes held inside one ``.smk`` file.

    :param path: the ``.smk`` capture file.
    :raises ValueError: if it holds no recognisable PNG.
    """
    with zipfile.ZipFile(path) as archive:
        items = json.loads(archive.read("items.json"))
    for item in items if isinstance(items, list) else [items]:
        data = item.get("image_data") if isinstance(item, dict) else None
        if not data:
            continue
        raw = base64.b64decode(data)
        if raw[:8] == PNG_MAGIC:
            return raw
    raise ValueError(f"{path} carries no PNG in items.json")


def size_of(raw: bytes) -> tuple[int, int]:
    """Return the (width, height) of PNG bytes, read from its IHDR chunk."""
    return struct.unpack(">II", raw[16:24])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="rewrite a PNG even when it is newer than its .smk")
    args = parser.parse_args()

    captures = sorted(SHOTS.glob("*.smk"))
    if not captures:
        print(f"No .smk files in {SHOTS}")
        return 0

    for capture in captures:
        png = capture.with_suffix(".png")
        if png.exists() and not args.force and png.stat().st_mtime >= capture.stat().st_mtime:
            print(f"up to date  {png}")
            continue
        try:
            raw = image_from_smk(capture)
        except (ValueError, KeyError, zipfile.BadZipFile) as exc:
            print(f"SKIPPED     {capture}: {exc}")
            continue
        png.write_bytes(raw)
        width, height = size_of(raw)
        print(f"wrote       {png}  {width}x{height}px  {len(raw) / 1024:.0f} KB")

    print(f"\nThe course publishes the PNGs in {SHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
