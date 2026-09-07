# Client Assignment Role — the User read grant, on production

Last Updated: 09-07-26 20:05 · Revision 1.0 — change log at the end.

Standing page with copy buttons: https://claude.ai/code/artifact/2bc5ad86-efa4-4618-ab0c-43adce3ae882
(*Client Assignment Role on Production*). This file is the repository record of
the same steps.

## 0. Read this first

**What is wrong.** A staff member whose only team is the **Client Administration
Team** cannot assign a mentor. Assigning writes the mentor's login User into
`assignedUsers` on the engagement, the client's contacts, the client profile and
the company, and EspoCRM refuses that write unless the acting user can *read*
every User being linked:

```
HTTP 403  No foreign record access for link operation (CEngagement:assignedUsers)
cannotRelateForbidden   foreignEntityType=User   action=read
```

The **Client Assignment Role** — the only role attached to that team — grants
nothing on the `User` scope. Cleveland has never seen the error because every
current member of the team is either an administrator or also sits on the Mentor
Team or the Mentor Administration Team, whose roles carry User read. The first
single-team user ever to press Assign was on the Lakeside rehearsal instance,
2026-09-07.

**The ruling (Doug, 2026-09-07):** the role becomes self-sufficient —
**`User: read all, edit own`**, the shape production's `ClientMentorIntakeRole`
already has.

**Where it stands.**

| Instance | State |
|---|---|
| Lakeside | Applied 2026-09-07, proven as a non-admin, Assign verified live by Doug |
| crm-test | Applied 2026-09-07, proven as a non-admin |
| **production** | **Not applied — this document** |

**Verified against the running instances, not from memory:** the link-check
source was read on both droplets (EspoCRM 9.3.4 and 10.0.6, identical); the
role's `data` was read back after each apply; the outside-in proof below was run
on both instances and produced the `PASS` line quoted. The DigitalOcean console
labels in section 3 are from memory and are marked so.

## 1. What changes, and what does not

One cell. The role's `data.User` goes from *not set* to
`{"read": "all", "edit": "own"}`. The script is merge-only: a level already at or
above the wanted one is left alone, nothing is lowered, nothing else on the role
is touched, and it reads the role back and rebuilds the cache.

**An administrator test proves nothing.** Administrators bypass the access
control list entirely, which is why this stayed invisible. The proof is section
3 step 8 — a throwaway regular user with only that team seat — and, on Monday, a
real one.

## 2. Before Sunday — ship the scripts and hold the credential

### 2a. In the terminal on this laptop (the repository)

The image builds from GitHub, so a script that is not pushed is not in the
container.

1. In the terminal whose prompt ends in `cbm-client-intake`, type the line below
   and press Enter:
   ```bash
   git log origin/main..main --oneline
   ```
   You should see four lines, the newest first: the probe script, the
   re-baseline note, the crm-test close-out, and `fix(crm): the Client
   Assignment Role can assign a mentor on its own (v0.221.1)`. If the list is
   empty or contains anything else, stop and tell me exactly what it lists.

2. In the same terminal, type the line below and press Enter:
   ```bash
   git push
   ```
   You should see a line ending `main -> main`. This deploys dev, crm-test and
   production together. If it reports a rejection or an error, stop and tell me
   exactly what it says.

3. Wait six minutes, then in the same terminal type the line below and press
   Enter:
   ```bash
   curl -s https://apps.clevelandbusinessmentors.org/healthz | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])"
   ```
   You should see `0.221.1`. If you see `0.221.0`, wait three more minutes and
   run it again; if it still says `0.221.0` after that, stop and tell me.

### 2b. In the production CRM, signed in as an administrator

Production has no `crm.config` account yet as far as the repository knows — the
account is created "once per instance" (skill `SETUP.md`) and crm-test's was
lost to the nightly reset and rebuilt today. Check before creating.

1. In the production CRM tab (`crm.clevelandbusinessmentors.org`), open
   **Administration**, then **Users**. Type `crm.config` in the search box and
   press Enter. You should see either one row, **CRM Configuration**, or an
   empty list. Note which.

2. **If the list was empty**: click **Create User** and fill exactly these
   boxes, leaving every other box as it is:

   | Box | Type exactly |
   |---|---|
   | User Name | `crm.config` |
   | First Name | `CRM` |
   | Last Name | `Configuration` |
   | Type | **Admin** |
   | Email Address | leave empty |
   | Is Active | on |

   For the password: generate a long random one in your password manager and
   save it there as *production crm.config*. If the create form shows
   **Password** and **Confirm Password** boxes, paste it into both now; if it
   does not, click **Save**, open the record, and use the dropdown beside
   **Edit** → **Change Password**. (I could not verify which of the two layouts
   this CRM version shows; the result is the same.) Click **Save**. You should
   see the record page for CRM Configuration with **Type: Admin**. If Type shows
   anything else, stop and tell me.

3. **If the row already existed**: open it. If the password is not in your
   password manager, use the dropdown beside **Edit** → **Change Password**,
   generate and store a new one as *production crm.config*, and click **Save**.

4. Two-factor authentication must be off for this account. If the CRM enforces
   it for administrators, this account needs the exemption — a script cannot
   answer a challenge, and the failure reads as a wrong password.

Nothing else is needed before Sunday. The password stays in the password manager
and is pasted once, into a silent prompt, in section 3.

## 3. Sunday 17:00 UTC — in the DigitalOcean console, inside the web container

Production admin credentials never come onto a laptop; the script runs where the
app's own environment is. These console labels are from memory — if a label
differs, stop and tell me what you see.

1. In the DigitalOcean tab, open **Apps**, then the app named
   **cbm-client-intake-prod**, then its **web** component, then the **Console**
   tab. You should see a shell prompt inside the container. If the tab is not
   there or the prompt never appears, stop and tell me what the page shows.

2. In that console, type the line below and press Enter:
   ```bash
   echo READY
   ```
   You should see `READY` on its own line. If not, the console is not accepting
   input yet — wait ten seconds and try once more; if still nothing, stop and
   tell me.

3. In that console, type the line below and press Enter. It takes the
   conformance check's *before* snapshot:
   ```bash
   cd /app && PYTHONPATH=/app .venv/bin/python scripts/preflight_crm.py --url "$ESPO_BASE_URL" --key "$ESPO_API_KEY" --json > /tmp/preflight-before.json; echo "exit=$?"
   ```
   You should see one line, `exit=` followed by a number. Write the number down.
   If the line does not appear or shows a traceback, stop and tell me exactly
   what it printed.

4. In that console, type the line below and press Enter. It names the CRM and
   the account for the script; nothing is printed:
   ```bash
   export ESPO_ADMIN_BASE="$ESPO_BASE_URL" ESPO_ADMIN_USER="crm.config"
   ```
   You should see the prompt again with nothing else. If anything is printed,
   stop and tell me what.

5. In that console, type the line below and press Enter. It opens a **silent**
   prompt for the password — what you paste will not appear on screen:
   ```bash
   stty -echo; printf 'crm.config password: '; read -r ESPO_ADMIN_PASS; stty echo; echo; export ESPO_ADMIN_PASS
   ```
   You should see `crm.config password: ` and the cursor waiting. Copy the
   *production crm.config* password from your password manager, paste it, and
   press Enter. You should then see an empty line and the prompt. **If any
   characters of the password appeared on screen** (the paste arrived before
   the prompt, or echo was on), the password is exposed: stop, change it in the
   CRM as in section 2b step 3, and tell me.

6. In that console, type the line below and press Enter. This is the dry run;
   it changes nothing:
   ```bash
   PYTHONPATH=/app .venv/bin/python scripts/migrate_client_assignment_role.py
   ```
   You should see, in this order: `CRM:  https://crm.clevelandbusinessmentors.org`,
   `User: crm.config (type=admin)`, `Mode: DRY RUN - nothing will change`, then
   under `CHANGES:` the two lines
   `WOULD set Client Assignment Role: User {read: (not set) -> all, edit: (not set) -> own}`
   and `WOULD rebuild`, and finally `Dry run only. Re-run with --apply to make
   these changes.` Three other outcomes:
   - `SKIPPED (already correct)` with the User levels already at `all` / `own`
     and no `CHANGES:` block: the grant is already on production — skip to
     step 8.
   - `Set ESPO_ADMIN_BASE, ESPO_ADMIN_USER, ESPO_ADMIN_PASS.`: step 4 or 5 did
     not take — repeat them.
   - Anything mentioning `401`, `Invalid username or password`, or
     `type=regular`: the account or its password is wrong — stop and tell me
     exactly what it printed.

7. In that console, type the line below and press Enter. This applies the
   change:
   ```bash
   PYTHONPATH=/app .venv/bin/python scripts/migrate_client_assignment_role.py --apply
   ```
   You should see `Mode: APPLY`, then under `CHANGES:` the line
   `set Client Assignment Role: User {read: (not set) -> all, edit: (not set) -> own} - read back OK: {'read': 'all', 'edit': 'own'}`
   and the line `rebuild -> HTTP 200`. If a `FAILED:` block appears, or
   `read back OK` is missing, stop and tell me exactly what it printed.

8. In that console, type the line below and press Enter. This is the proof as a
   real non-admin: it creates a throwaway regular user whose only team is the
   Client Administration Team, reads one other user's record as them, and
   deletes the throwaway user again — whatever the outcome:
   ```bash
   PYTHONPATH=/app .venv/bin/python scripts/probe_user_read_grant.py --team "Client Administration Team" --apply
   ```
   You should see `created User/…('acl.probe')`, a line ending `-> HTTP 200`,
   the line `RESULT: PASS - the role grants User read; Assign will not be
   refused for this.`, and `deleted User/…('acl.probe')`. If you see
   `RESULT: FAIL`, `RESULT: INCONCLUSIVE`, or `could not delete`, stop and tell
   me exactly what it printed.

9. In that console, type the line below and press Enter. It takes the *after*
   snapshot and compares it with the one from step 3:
   ```bash
   PYTHONPATH=/app .venv/bin/python scripts/preflight_crm.py --url "$ESPO_BASE_URL" --key "$ESPO_API_KEY" --json > /tmp/preflight-after.json; echo "exit=$?"; cmp /tmp/preflight-before.json /tmp/preflight-after.json && echo UNCHANGED
   ```
   You should see `exit=` with the same number as in step 3, then `UNCHANGED`.
   A role grant does not change the schema, so the two snapshots must match
   byte for byte. If the numbers differ or `UNCHANGED` does not appear, do not
   undo anything — stop and tell me both numbers.

10. In that console, type the line below and press Enter. It clears the
    password from the shell and closes the console:
    ```bash
    unset ESPO_ADMIN_PASS; exit
    ```
    You should see the console close or the prompt disappear. Nothing else.

## 4. Monday — in the production app, as a real non-admin

This is the compensating control for an unattended Sunday cut, and the only test
that is not an administrator.

1. In a browser, open https://apps.clevelandbusinessmentors.org/ and sign in as
   a **real member of the Client Administration Team who is not an
   administrator** — not your own admin login. You should see the portal with
   a **Client Administration** tile. If the tile is missing, that user is not
   on the team — stop and tell me who you used.

2. Open **Client Administration**. Right-click any row that already has a
   mentor and choose **Repair assignment…**, then confirm. The repair re-runs
   the same `assignedUsers` write as an assignment without changing the
   engagement's mentor, status or date, and sends no email. You should see the
   row's confirmation and no red error. If a red error appears that mentions
   *security*, *forbidden*, or *permission*, stop and tell me its exact wording.

3. Tell me the result. I then close the production line of `OPEN-ITEMS.md`
   item 28 and mark this document built.

## 5. If it goes wrong

The change is one cell on one role, and the rollback is the CRM's own screen —
no script and no deploy:

1. In the production CRM tab, as an administrator, open **Administration** →
   **Roles** → **Client Assignment Role** → **Edit**.
2. In the **User** row, set **Read** to *not set* and **Edit** to *not set*.
   Click **Save**.
3. Open **Administration** → **Clear Cache**. Assignment then behaves exactly as
   it did before Sunday, including the refusal for single-team members.

Nothing else on production was touched. The throwaway `acl.probe` user is
soft-deleted (an administrator's user list can still show it under *deleted*);
EspoCRM's own cleanup job removes it on its schedule.

## 6. The scripts

- `scripts/migrate_client_assignment_role.py` — the change. Idempotent,
  merge-only, dry-run by default, admin login from the environment, reads back
  and rebuilds. The same script did Lakeside and crm-test.
- `scripts/probe_user_read_grant.py` — the outside-in proof. Creates, checks and
  deletes a throwaway single-team regular user; `--apply` to run, exit 0 on
  `PASS`.
- `scripts/preflight_crm.py` — the read-only conformance check used for the
  before/after snapshot.

Which credential each one uses is fixed by EspoCRM, not by choice: a role write
is administrator-only, so the first two run as the dedicated `crm.config`
account; the conformance check needs only the org-wide API key.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-07-26 20:05 | Claude (Claude Code) | First version, written after the Lakeside and crm-test applies of 2026-09-07 |
