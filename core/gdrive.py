"""Delegated Google Drive access for the Documents tab (DOC-MGMT Phase 1).

One :class:`DriveClient` per uploader: the shared Google service account (the
same key Gmail/Calendar use) mints a short-lived access token with domain-wide
delegation, impersonating exactly ONE ``@cbmentors.org`` user (``subject``) —
the signed-in manager, resolved from their own CRM identity
(``CMentorProfile.cbmEmail``), never from request input. Drive audit logs
therefore attribute every upload to the actual person (PRD decision D-01's
rationale, kept under the web adaptation).

All operations target ONE shared drive ("CBM Documents") and carry
``supportsAllDrives=true``. Files keep their native MIME type — conversion to
Google editor formats is never requested (PRD decision D-04). Uploads over
5 MB use a resumable session (DOC-01); Drive-side 403 rate limits and 5xx are
retried with exponential backoff (NFR-02).

Plain REST via httpx (like :mod:`core.gcalendar`) — no google-api-python-client
dependency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

import httpx

log = logging.getLogger("cbm_intake.gdrive")

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"

_BASE = "https://www.googleapis.com/drive/v3"
_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

FOLDER_MIME = "application/vnd.google-apps.folder"

# The metadata captured for every uploaded file (PRD DOC-01).
FILE_FIELDS = "id,name,webViewLink,modifiedTime,md5Checksum"

# Google-native editor formats have no native bytes — in-app viewing exports
# them to PDF (PRD DOC-04).
PDF_MIME = "application/pdf"
GOOGLE_NATIVE_MIMES = frozenset(
    {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        "application/vnd.google-apps.presentation",
    }
)

# Uploads at or under this size go up in one multipart request; anything larger
# uses a resumable session (PRD DOC-01: "resumable upload for files over 5 MB").
RESUMABLE_THRESHOLD = 5 * 1024 * 1024
# Resumable chunk size — must be a multiple of 256 KiB per the Drive API.
CHUNK_SIZE = 8 * 1024 * 1024

_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = 0.5


class DriveError(Exception):
    """Any Drive API / auth failure."""


def _retryable(resp: httpx.Response) -> bool:
    """NFR-02: retry 5xx and 403 *rate-limit* responses (never other 403s)."""
    if resp.status_code >= 500 or resp.status_code == 429:
        return True
    if resp.status_code == 403:
        return b"ratelimitexceeded" in resp.content.lower().replace(b" ", b"")
    return False


class DriveClient:
    """Drive REST for ONE shared drive, authenticated by delegated impersonation."""

    def __init__(
        self,
        service_account_info: dict[str, Any],
        mailbox: str,
        drive_id: str,
        timeout: int = 60,
    ) -> None:
        self.mailbox = mailbox
        self.drive_id = drive_id
        self._info = service_account_info
        self._timeout = timeout
        self._tokens: dict[str, tuple[str, float]] = {}  # scope -> (token, expiry)

    # --- auth (same shape as core.gcalendar) --------------------------------

    async def _token(self, scope: str = DRIVE_SCOPE) -> str:
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account

            def mint() -> tuple[str, float]:
                creds = service_account.Credentials.from_service_account_info(
                    self._info, scopes=[scope], subject=self.mailbox
                )
                creds.refresh(Request())
                expiry = creds.expiry.timestamp() if creds.expiry else time.time() + 1800
                return creds.token, expiry

            token, expiry = await asyncio.to_thread(mint)
        except Exception as exc:  # bad key, delegation not authorized, network, …
            raise DriveError(f"Drive auth failed for {self.mailbox}: {exc}") from exc
        self._tokens[scope] = (token, expiry)
        log.info("drive access as %s", self.mailbox)
        return token

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        content: Optional[bytes] = None,
        headers: Optional[dict[str, str]] = None,
        ok_statuses: tuple[int, ...] = (),
    ) -> httpx.Response:
        """One authorized request, with backoff retries on rate-limit/5xx."""
        token = await self._token()
        hdrs = {"Authorization": f"Bearer {token}"}
        if headers:
            hdrs.update(headers)
        last: Optional[httpx.Response] = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        method, url, params=params, json=json_body,
                        content=content, headers=hdrs,
                    )
            except httpx.HTTPError as exc:
                raise DriveError(f"Drive request failed ({url}): {exc}") from exc
            if resp.status_code < 400 or resp.status_code in ok_statuses:
                return resp
            last = resp
            if not _retryable(resp) or attempt == _MAX_ATTEMPTS - 1:
                break
            await asyncio.sleep(_BACKOFF_SECONDS * (2**attempt))
        assert last is not None
        raise DriveError(
            f"Drive {method} {url.split('?')[0]} for {self.mailbox}: "
            f"HTTP {last.status_code} {last.text[:300]}"
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        ok_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        resp = await self._send(
            method, f"{_BASE}{path}", params=params, json_body=json_body,
            ok_statuses=ok_statuses,
        )
        return resp.json() if resp.content and resp.status_code < 400 else {}

    # --- folders -------------------------------------------------------------

    async def find_child_folder(self, parent_id: str, name: str) -> Optional[str]:
        """The id of the folder named ``name`` directly under ``parent_id``
        (the shared drive's root is ``drive_id`` itself), or None."""
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        data = await self._request(
            "GET",
            "/files",
            params={
                "q": (
                    f"name = '{escaped}' and '{parent_id}' in parents "
                    f"and mimeType = '{FOLDER_MIME}' and trashed = false"
                ),
                "driveId": self.drive_id,
                "corpora": "drive",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "fields": "files(id,name)",
                "pageSize": 10,
            },
        )
        files = data.get("files") or []
        return files[0]["id"] if files else None

    async def create_folder(self, parent_id: str, name: str) -> str:
        data = await self._request(
            "POST",
            "/files",
            params={"supportsAllDrives": "true", "fields": "id"},
            json_body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        )
        log.info("drive folder created as %s -> %s (%s)", self.mailbox, name, data.get("id"))
        return data["id"]

    # --- files ----------------------------------------------------------------

    async def upload_file(
        self, folder_id: str, filename: str, mime_type: str, data: bytes
    ) -> dict[str, Any]:
        """Upload ``data`` into ``folder_id`` with its NATIVE MIME type (D-04 —
        no conversion to Google editor formats is ever requested). Returns the
        Drive file resource (:data:`FILE_FIELDS`)."""
        if len(data) > RESUMABLE_THRESHOLD:
            file = await self._upload_resumable(folder_id, filename, mime_type, data)
        else:
            file = await self._upload_multipart(folder_id, filename, mime_type, data)
        log.info(
            "drive upload as %s -> %s (%s, %d bytes)",
            self.mailbox, file.get("id"), filename, len(data),
        )
        return file

    async def _upload_multipart(
        self, folder_id: str, filename: str, mime_type: str, data: bytes
    ) -> dict[str, Any]:
        boundary = f"cbm-{uuid.uuid4().hex}"
        meta = json.dumps({"name": filename, "parents": [folder_id]})
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{meta}\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--".encode()
        resp = await self._send(
            "POST",
            f"{_UPLOAD_BASE}/files",
            params={
                "uploadType": "multipart",
                "supportsAllDrives": "true",
                "fields": FILE_FIELDS,
            },
            content=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
        return resp.json()

    async def _upload_resumable(
        self, folder_id: str, filename: str, mime_type: str, data: bytes
    ) -> dict[str, Any]:
        start = await self._send(
            "POST",
            f"{_UPLOAD_BASE}/files",
            params={
                "uploadType": "resumable",
                "supportsAllDrives": "true",
                "fields": FILE_FIELDS,
            },
            json_body={"name": filename, "parents": [folder_id]},
            headers={
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(len(data)),
            },
        )
        session_url = start.headers.get("Location")
        if not session_url:
            raise DriveError("Drive did not return a resumable upload session URL.")
        total = len(data)
        offset = 0
        while offset < total:
            chunk = data[offset : offset + CHUNK_SIZE]
            end = offset + len(chunk) - 1
            resp = await self._send(
                "PUT",
                session_url,
                content=chunk,
                headers={
                    "Content-Type": mime_type,
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                },
                ok_statuses=(308,),
            )
            if resp.status_code == 308:  # chunk stored, session continues
                offset = end + 1
                continue
            return resp.json()
        raise DriveError("Drive resumable upload ended without a completed file.")

    async def download_file(self, file_id: str) -> bytes:
        """The file's native bytes (``files.get?alt=media`` — DOC-03)."""
        resp = await self._send(
            "GET",
            f"{_BASE}/files/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
        )
        log.info(
            "drive download as %s -> %s (%d bytes)",
            self.mailbox, file_id, len(resp.content),
        )
        return resp.content

    async def export_pdf(self, file_id: str) -> bytes:
        """A Google-native file (Docs/Sheets/Slides) exported to PDF (DOC-04).
        Note the Drive export cap (~10 MB of exported content) — an oversized
        document raises a DriveError; the caller falls back to Open in Drive."""
        resp = await self._send(
            "GET",
            f"{_BASE}/files/{file_id}/export",
            params={"mimeType": PDF_MIME},
        )
        log.info(
            "drive pdf export as %s -> %s (%d bytes)",
            self.mailbox, file_id, len(resp.content),
        )
        return resp.content

    async def list_folder_files(self, folder_id: str) -> list[dict[str, Any]]:
        """Every non-trashed file directly inside ``folder_id`` (one
        ``files.list`` scoped to the record folder — the DOC-02 lazy
        modifiedTime refresh)."""
        files: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            params: dict[str, Any] = {
                "q": (
                    f"'{folder_id}' in parents and trashed = false "
                    f"and mimeType != '{FOLDER_MIME}'"
                ),
                "driveId": self.drive_id,
                "corpora": "drive",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._request("GET", "/files", params=params)
            files.extend(data.get("files") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                return files

    async def delete_file(self, file_id: str) -> None:
        """Rollback only (DOC-01): remove a Drive file that has no metadata row.
        Already-gone (404) counts as done."""
        await self._send(
            "DELETE",
            f"{_BASE}/files/{file_id}",
            params={"supportsAllDrives": "true"},
            ok_statuses=(404,),
        )
        log.info("drive file deleted (rollback) as %s -> %s", self.mailbox, file_id)
