# CRM handoff — convert `CSponsorProfile.description` (Funder Notes) from text to wysiwyg

Last Updated: 10-11-26 14:10 · Revision 1.0

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

## 0. Current state (read live 10-11-26)

- crm-test: `entityDefs.CSponsorProfile.fields.description.type` = `text`.
  The customization file
  `/var/www/html/custom/Espo/Custom/Resources/metadata/entityDefs/CSponsorProfile.json`
  (inside the `espocrm` container on droplet CBM-TEST, 104.131.45.208) already
  carries `fields.description: {"type": "text"}` — the change is a one-key
  edit of that entry. `CPartnerProfile.partnerNotes` and
  `CEngagement.description` are already `wysiwyg` there.
- Production: not probed from here; the same check and the same edit apply.
- Entity Manager cannot change an existing field's type, and neither can
  the CRM-plan applier; the file-level override is EspoCRM's standard path.
  text → wysiwyg keeps the same TEXT column: **no data migration, no data
  loss**. Existing plain notes stay stored verbatim; the editor up-converts
  line breaks when it opens.

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
crm-test), within a minute (the metadata cache):

1. Funder Management → any funder → the Overview's **Funder Notes** panel
   opens the rich editor with its toolbar, not the plain box.
2. A funder with existing plain notes: line breaks survive into the editor
   and back through a save.
3. Paste or insert an image, save, reopen: the image comes back. A 403
   naming `Attachment` create means the Sponsor Manager Role lacks the
   Attachment create grant — grant it on the role, on both instances.
4. The same funder in the EspoCRM UI shows the notes as rich text with the
   image (the CRM proves the attachment was bound).

## 3. Then production and Boston

Same one-key edit of the production instance's
`custom/Espo/Custom/Resources/metadata/entityDefs/CSponsorProfile.json`,
same rebuild, same verification including the non-admin pass. Until it
runs, production's Funder Notes stays the plain box it is today — the app
detects `text` and changes nothing.

## Change log

| Rev | Date | Author | Change |
|---|---|---|---|
| 1.0 | 10-11-26 14:10 | Claude (Claude Code) | First version, with the v0.252.0 build. |
