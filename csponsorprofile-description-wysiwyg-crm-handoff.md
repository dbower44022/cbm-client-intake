# CRM handoff — convert `CSponsorProfile.description` (Funder Notes) from text to wysiwyg

Last Updated: 10-11-26 18:55 · Revision 1.1

**Why:** Doug, 2026-10-11: *"The funder notes should be wysiwyg."* The Funder
Management Overview's notes panel and the Details tab's Notes field should
hold rich text and pasted or picked images. The app side ships
feature-detected (v0.252.0): the Overview's editor follows the field's LIVE
type (`sessions.service.live_notes_type`) and the Details tab already
renders from live metadata, so each CRM upgrades the moment its field is
converted, with no deploy. Images ride the inline-attachment pattern, which
is why the field's *type* must really be `wysiwyg`: EspoCRM's Wysiwyg saver
binds an attachment only on a wysiwyg field; on a `text` field the cleanup
job would collect it later. This is the `CEngagement.description` recipe
(`cengagement-description-wysiwyg-crm-handoff.md`) applied to the funder.

## 0. Current state (read live 10-11-26 18:40)

- crm-test: **converted.** `entityDefs.CSponsorProfile.fields.description.type`
  = `wysiwyg`, read as the org-wide key — Doug ran § 1 on 10-11-26 between
  14:12 (still `text`) and 14:30. What the first look showed was the plain
  box still, which was v0.252.1 (the app read a scalar metadata key that
  EspoCRM answers unquoted), fixed and live the same afternoon.
  The customization file
  `/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/CSponsorProfile.json`
  (inside the `espocrm` container on droplet CBM-TEST, 104.131.45.208) already
  carried `fields.description: {"type": "text"}` — the change was a one-key
  edit of that entry. `CPartnerProfile.partnerNotes` and
  `CEngagement.description` are `wysiwyg` there too.
- Production and Boston: not probed from here (no credentials in this
  environment); still `text` until § 3 runs. The same check and the same
  edit apply.
- Entity Manager cannot change an existing field's type, and neither can
  the CRM-plan applier; the file-level override is EspoCRM's standard path.
  text → wysiwyg keeps the same TEXT column: **no data migration, no data
  loss**. Existing plain notes stay stored verbatim. **The app up-converts
  them (escape + `<br>`) when the rich editor or a read view opens, from
  v0.252.2** — before that build the session tools handed the plain value
  straight to the editor, where HTML collapses its line breaks into one run,
  and the first save would have stored it that way (the sentence in revision
  1.0 claiming otherwise was carried over from the engagement recipe, which
  is true of Client Administration only). Step 2.2 is the check; run it on a
  build reporting v0.252.2 or later on `/healthz`.

## 1. Apply on crm-test

One SSH session, by Doug (a mutating SSH command). Not between 04:00 and
05:00 UTC, the reset window. The heredoc makes a timestamped backup, flips
the one key, and rewrites the file in its existing style:

```bash
ssh root@104.131.45.208
docker exec -u www-data espocrm php -r '
  $p = "/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/CSponsorProfile.json";
  copy($p, $p . ".bak-desc-wysiwyg");
  $d = json_decode(file_get_contents($p), true);
  if ($d === null) { fwrite(STDERR, "JSON parse failed - aborting\n"); exit(1); }
  $d["fields"]["description"]["type"] = "wysiwyg";
  file_put_contents($p, json_encode($d, JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE));
  echo "description is now: ", json_encode($d["fields"]["description"]), "\n";
'
docker exec -u www-data espocrm php command.php rebuild
```

The edit lives in `custom/`, which the nightly sandbox reset rebuilds
**from**, so it survives the reset by design.

## 2. Verify

As the org-wide key (read-only):

```bash
curl -s -H "X-Api-Key: $ESPO_API_KEY" \
  'https://crm-test.clevelandbusinessmentors.org/api/v1/Metadata?key=entityDefs.CSponsorProfile.fields.description'
```

Expected `{"type":"wysiwyg", ...}`. Then the app, **as a real non-admin
member of the Sponsor Management Team** (`sally.sponsor@cbmentors.org` on
crm-test), within a minute (the metadata cache), on a build of **v0.252.2 or
later** (the footer, or `/healthz`):

1. Funder Management → any funder → the Overview's **Funder Notes** panel
   opens the rich editor with its toolbar, not the plain box. The same
   funder's **Details** tab, panel **Funder notes**, shows the field as rich
   text in view mode and opens the same editor under that panel's Edit — it
   renders from live metadata and upgrades with the Overview.
2. A funder with existing plain notes: line breaks survive into the editor,
   in the Overview's read view and its View pop-up, and back through a save.
   Collapsed-into-one-run notes mean the build is older than v0.252.2.
3. Paste or insert an image, save, reopen: the image comes back. A 403
   naming `Attachment` create means the Sponsor Manager Role lacks the
   Attachment create grant — grant it on the role, on both instances.
4. The same funder in the EspoCRM UI shows the notes as rich text with the
   image (the CRM proves the attachment was bound).

## 3. Then production and Boston

At a Sunday 17:00 UTC slot, by a human, one instance at a time. Hosts,
containers and the SSH route per instance are in
`prds/chapter-network/crm-update-runbook.md` (Boston's CRM is its own
droplet, `crm.bbmentors.org`). Same one-key edit of that instance's
`custom/Espo/Custom/Resources/metadata/entityDefs/CSponsorProfile.json`,
same rebuild, same verification including the non-admin pass — the
Attachment-create grant on the Sponsor Manager Role must be confirmed on each
instance separately, because roles drift between CRMs.

Two things the § 1 heredoc assumes that may not hold off crm-test. If the
file carries no `description` entry yet, the heredoc still works: PHP creates
the key, and the result is `{"type": "wysiwyg"}`. If the file does not exist
at all (possible on Boston, whose CRM was built from the standard), the heredoc
aborts on the JSON parse and writes nothing; create the file first with the
one entry:

```json
{"fields": {"description": {"type": "wysiwyg"}}}
```

Until the edit runs, that instance's Funder Notes stays the plain box it is
today — the app detects `text` and changes nothing.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.1 | 10-11-26 18:55 | Claude (Claude Code) | Review fixes. § 0: crm-test converted (read live); the line-break claim corrected — the session tools up-convert only from v0.252.2, built with this revision. § 2: the pass needs v0.252.2, checks the Details tab too, and names the collapsed-note symptom. § 3: Boston named, runbook pointer, the missing-entry and missing-file cases. |
| 1.0 | 10-11-26 14:10 | Claude (Claude Code) | First version, with the v0.252.0 build. |
