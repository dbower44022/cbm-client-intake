# CRM handoff — convert `CEngagement.description` from text to wysiwyg

**Why:** the Client Administration Notes column (and the popup's "Internal
notes" field) should hold rich text and pasted/picked images. The app side
shipped feature-detected (v0.218.0): it probes this field's live type per load
and keeps the plain textarea until the CRM reports `wysiwyg`, then upgrades
with no deploy. Images ride the established inline-attachment pattern — the
EspoCRM Wysiwyg saver binds each attachment to the engagement on save, which is
exactly why the field's *type* must really be `wysiwyg`: an attachment
referenced from a plain-`text` field is never bound, and EspoCRM's cleanup job
would silently collect it later.

## 0. Read this first — current state

Verified live on **crm-test** 2026-08-31 (metadata read with the org API key;
file read over SSH into the `espocrm` container):

- `entityDefs.CEngagement.fields.description.type` = `text`.
- The customization file
  `/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/CEngagement.json`
  (inside the `espocrm` container on droplet CBM-TEST, 104.131.45.208) already
  carries a `fields.description` entry: `{"type": "text"}`. The change is a
  one-key edit of that existing entry, **not** a new file.
- Entity Manager cannot make this change — EspoCRM does not offer changing an
  existing field's type in the UI. The file-level metadata override is the
  standard EspoCRM customization for exactly this (text → wysiwyg keeps the
  same TEXT storage column, so **no data migration and no data loss**; existing
  plain-text notes stay stored verbatim and the app up-converts line breaks
  when the editor opens).
- **The `crm.config` admin login is currently rejected on crm-test**
  ("Service account credentials were rejected", 2026-08-31), so the API-side
  admin tooling could not be used and could not probe whether
  `PUT Admin/fieldManager/CEngagement/description` would accept a type change.
  Worth fixing regardless of this handoff (see the espo-crm-changes skill's
  SETUP.md); the file-level path below does not need it.
- **Production was not probed** (no prod credentials in this environment). The
  same check and the same change apply there; paths/hosting are per the
  chapter-network runbook.

## 1. Apply on crm-test

One SSH session. The heredoc PHP makes a timestamped backup, flips the one key,
and pretty-prints the JSON back in the file's existing 4-space style:

```bash
ssh root@104.131.45.208
docker exec -u www-data espocrm php -r '
  $p = "/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/CEngagement.json";
  copy($p, $p . ".bak-desc-wysiwyg");
  $d = json_decode(file_get_contents($p), true);
  if ($d === null) { fwrite(STDERR, "JSON parse failed - aborting\n"); exit(1); }
  $d["fields"]["description"]["type"] = "wysiwyg";
  file_put_contents($p, json_encode($d, JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE));
  echo "description is now: ", json_encode($d["fields"]["description"]), "\n";
'
docker exec -u www-data espocrm php command.php rebuild
```

The edit lives in `custom/`, which the nightly sandbox reset rebuilds **from**,
so it survives the reset by design.

⚠ Do not run this between 04:00 and 05:00 UTC (the reset window).

## 2. Verify — read the data back

```bash
curl -s -H "X-Api-Key: $ESPO_API_KEY" \
  'https://crm-test.clevelandbusinessmentors.org/api/v1/Metadata?key=entityDefs.CEngagement.fields.description'
```

Expected: `{"type":"wysiwyg", ...}`. Anything still saying `"text"` means the
rebuild didn't run or the edit landed in the wrong file.

Then the app side, **as a real non-admin member of the Client Administration
Team** (an admin bypasses ACL and proves nothing):

1. Open `/assignments` — the Notes column should now open the rich editor
   (toolbar incl. the Insert-image button) instead of the plain textarea.
2. An engagement with existing plain notes: line breaks must survive into the
   editor and back through a save.
3. Paste or insert an image, save, reopen — the image must come back. **If the
   upload fails with a 403 naming `Attachment` create, that staff role is
   missing the Attachment create grant** — the same grant the mentor role
   needed for profile photos (found live 2026-07-14). Grant it on the role, on
   both instances.
4. Open the same engagement in the EspoCRM UI — the description shows as rich
   text and renders the image (the CRM proves the attachment got bound).

## 3. Then production

At the Sunday 17:00 UTC slot, by a human. Same one-key edit of
`custom/Espo/Custom/Resources/metadata/entityDefs/CEngagement.json` on the
production instance, same rebuild, same verification — including the non-admin
pass, because prod's roles drift from crm-test's and the Attachment-create
grant must be confirmed there separately. Until this runs, prod's Notes column
simply stays the plain textarea it is today (the app detects `text` and changes
nothing).
