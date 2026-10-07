# Changing a chapter's colours

Last Updated: 10-07-26 03:48 · Revision 1.0 — see the change log at the end.

A deployment's colours come from one small stylesheet, called **the colour
file**, that the chapter hosts on the web. The setting `CHAPTER_TOKENS_URL`
holds the colour file's web address. Every page the application serves loads
the colour file right after the built-in colours, so each colour the file names
replaces the built-in one. Each colour the file leaves out keeps Cleveland's
value.

The colour file sets **design tokens**. A design token is a named colour value,
such as `--cbm-navy`, that the pages read their colour from. The full list of
design tokens is in `frontend/shared/tokens.css`.

This document is the step-by-step companion to deployment guide step 6.5
(`prds/chapter-network/deployment-guide/guide/06-build-the-chapter-s-public-website.md`),
which says *what* a chapter supplies. This document says how to enter the
address on a running deployment, how to check the result, where each colour
appears, and how to go back.

## Where each colour is applied

Checked against the stylesheets in the code at v0.232.0, not by looking at
every page in a browser.

**Primary colour** — design token `--cbm-navy`, Cleveland's value `#173B60`.

- Every heading on every page.
- The background of second-rank buttons, such as Back, Cancel, Reload and
  Sign out.
- The accent colour in the portal, the intake forms and every staff
  application except System Settings.
- The header bar and hero banner of the public webinar page.

**Button colour** — design token `--cbm-gold`, Cleveland's value `#CB963B`.

- Every main action button, such as Next and Submit Request on the intake
  forms and Save in the edit dialogs.
- A few accents in the portal, Workspace Directories, Submission Admin,
  My Email, My Mentor Profile, the session tools and Events.
- The strapline band and the menu underline on the public webinar page.

**Button hover colour** — design token `--cbm-btn-bg-hover`, Cleveland's value
`#b8842f`.

- Main action buttons while the mouse pointer is over them. Nowhere else.

**Body text colour** — design token `--cbm-text`, Cleveland's value `#7A7A7A`.

- The default text colour of every page.
- Secondary text in Client Administration, Mentor Administration, Workspace
  Directories, My Mentor Profile, Submission Admin and the address paste
  helper.

### What the colour file does not change

- **The public webinar calendar and recorded-library panels.** Their
  stylesheet is a copy of the marketing website's own and uses fixed colours,
  so they stay Cleveland's colours. The same is true of the staff website
  preview in Events.
- **Second-rank buttons while the mouse pointer is over them.** That hover
  colour is fixed at Cleveland's dark navy `#0f2942`
  (`frontend/shared/tokens.css`), so it clashes with a different primary
  colour.
- **The System Settings page's own tables and chips.** Its headings and
  buttons do follow the colour file.
- **The portal's birthday confetti**, which includes Cleveland's gold.
- **Greys and status colours.** Every application has fixed greys of its own.
  The green, amber and red status colours are separate design tokens that the
  four-colour template does not touch.
- **Anything outside this application:** the CRM, emails sent from CRM email
  templates, the marketing website and Google Drive.

## Section 1 · On your computer: write the colour file

The colour file is plain text. It must set design tokens inside `:root` and
nothing else.

1. On your computer, open a plain-text editor:
   - Text Editor on Linux.
   - Notepad on Windows.
   - TextEdit on a Mac, after choosing Format → Make Plain Text.

   You should see an empty document.
2. In the plain-text editor's empty document, paste these six lines:
   ```css
   :root {
     --cbm-navy: PRIMARY-COLOUR;
     --cbm-gold: BUTTON-COLOUR;
     --cbm-btn-bg-hover: BUTTON-HOVER-COLOUR;
     --cbm-text: BODY-TEXT-COLOUR;
   }
   ```
   You should see six lines. The first ends in `{` and the last is `}` on
   its own.
3. In the plain-text editor, replace each of the four capitalised placeholders
   with a colour code. A colour code is `#` followed by six letters or digits,
   such as `#2E7D32`. To keep Cleveland's value for one colour, delete that
   colour's whole line instead. You should see every remaining middle line end
   in a colour code and a semicolon, such as `--cbm-gold: #2E7D32;`, with no
   capitalised placeholder left.
4. In the plain-text editor, save the document as `chapter-tokens.css`. You
   should see a file named exactly `chapter-tokens.css`. If the name ends in
   `.css.txt`, stop and tell the central support organization exactly what
   name you see.

## Section 2 · On the web host: publish the colour file

Browsers fetch the colour file directly, so the colour file needs its own
public web address. Browsers ignore a stylesheet from another site unless the
host labels it `text/css`.

1. Upload `chapter-tokens.css` to the chapter's website so that it has its own
   address, such as `https://WEBSITE-DOMAIN/chapter-tokens.css`. The upload
   screen differs from host to host, so this document cannot name it. If the
   chapter's website cannot serve a `.css` file, the central support
   organization hosts the colour file somewhere else. You should end up with a
   full web address that starts with `https://` and ends with `.css`. The
   steps below call it COLOUR-FILE-ADDRESS.
2. In a terminal, type this line with COLOUR-FILE-ADDRESS replaced by the
   colour file's full web address, then press Enter:
   ```bash
   curl -sI COLOUR-FILE-ADDRESS
   ```
   You should see a first line ending in `200` and a line reading
   `content-type: text/css`. If the first line does not end in 200, or the
   type is not `text/css`, stop and tell the central support organization
   exactly what you see.

## Section 3 · In the browser: enter the address in System Settings

Do this on crm-test first, then on the real deployment. A System Settings
change on crm-test survives the nightly reset. The deployment addresses are:

- crm-test: `https://cbm-client-intake-svxs3.ondigitalocean.app`
- Cleveland production: `https://apps.clevelandbusinessmentors.org`
- Boston: `https://apps.bbmentors.org`

1. In the browser's address bar, type the deployment's address followed by
   `/setup/`, then press Enter. For crm-test that is
   `https://cbm-client-intake-svxs3.ondigitalocean.app/setup/`. You should see
   the System Settings page with five tabs: Settings, Feature readiness,
   Environment diff, Operations and History. If a sign-in form appears first,
   sign in with a CRM administrator account; only CRM administrators can open
   this page. If you see anything else, stop and tell the central support
   organization exactly what you see.
2. On the Settings tab of the System Settings page, click the **Filter
   settings…** box and type `design-token`. You should see one row, **Chapter
   design-token override**, under the heading Presentation, with the chip
   **Default**.
3. On that row, click the name **Chapter design-token override**. You should
   see a dialog titled **Change setting**.
4. In the Change setting dialog, click the **Value** box and paste
   COLOUR-FILE-ADDRESS, the colour file's web address from section 2. You
   should see the address, starting with `https://`, in the Value box.
5. In the Change setting dialog, click the **Reason** box and type
   `Chapter colours`. You should see Chapter colours in the Reason box. The
   reason is recorded on the History tab.
6. In the Change setting dialog, leave **Temporary — remind me to review it**
   unticked. Leave both boxes under **Roll out to specific teams or people
   only** empty. A value limited to teams or people is never used for page
   colours, so the colours would not change. You should see the Temporary box
   unticked and both roll-out boxes empty.
7. In the Change setting dialog, click **Save**. You should see the dialog
   close. The Chapter design-token override row should now show the address
   and the chip **Override**. If a message says the change was undone or could
   not be checked, stop and tell the central support organization exactly what
   it says.

## Section 4 · In the browser: check the colours

The running application picks up the new setting within about a minute
(`SETUP_REFRESH_SECONDS`, default 45).

1. Wait one minute. In a new browser tab, type the deployment's address
   followed by `/client-intake/`, then press Enter. You should see the client
   intake form.
2. On the client intake form, press **Ctrl+Shift+R** (on a Mac,
   **Cmd+Shift+R**). This reloads the page without the browser's saved copy.
   You should see the headings in the new primary colour and the Next button
   in the new button colour. If they are still Cleveland's navy and gold, stop
   and tell the central support organization exactly what you see.
3. On the client intake form, move the mouse pointer over **Next** without
   clicking. You should see the Next button change to the new button hover
   colour.
4. In the same tab, type the deployment's address followed by `/`, press
   Enter, and sign in if asked. You should see the portal in the new colours.
   Open one staff application tile to confirm the staff applications changed
   too.

## Section 5 · Changing the colours again later

Browsers can keep an old copy of the colour file for a while. A new file name
makes every browser fetch the new colours at once.

1. On your computer, edit the colours as in section 1, step 3. Save the file
   under a new name, such as `chapter-tokens-2.css`. You should see a file
   named `chapter-tokens-2.css` beside the old one.
2. Publish and check `chapter-tokens-2.css` exactly as in section 2, then
   enter its address exactly as in section 3. You should see the new address
   on the Chapter design-token override row, and the new colours when you
   repeat the section 4 check.

## Section 6 · In System Settings: go back to Cleveland's colours

1. On the Settings tab of the System Settings page, type `design-token` in
   **Filter settings…**, then click the name **Chapter design-token
   override**. You should see the Change setting dialog.
2. In the Change setting dialog, click **Reset to deployment value**. You
   should see the dialog close and the row show the chip **Default** with no
   address. Pages go back to Cleveland's colours within about a minute. If the
   row shows anything other than Default, stop and tell the central support
   organization exactly what you see.

## How it works, for engineers

- `core/branding.render_page` inserts a `<link>` to the colour file directly
  after the `/shared/tokens.css` link on every served page. A page that does
  not load the design tokens gets no link.
- The setting is `chapter_tokens_url` (`core/config.py`), editable at `/setup`
  in the Presentation group (`core/settings_registry.py`). It is read per
  request, so no restart is needed.
- `core/branding.brand_key` includes the address, so changing the address
  drops the rendered-page cache and its ETags. Changing the *contents* of the
  colour file at the same address does not; that is why section 5 uses a new
  file name.
- A scoped override (teams or people) is excluded from the process-wide
  settings and so never reaches `render_page`.
- `scripts/chapter_form/to_values.py` writes a colour file from the four
  colour answers on the chapter information page (`COLOUR_TOKENS`).
- No deployment has used the setting yet (10-07-26). The injection is covered
  by `tests/test_shared_branding.py`; the live path has never been watched.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-07-26 03:48 | Claude (Claude Code) | First version, from the colour sweep of 09-29-26 against v0.232.0. Chosen by Doug over a tokens.css fix for the second-rank hover colour, which is still owed. |
