# Claude Code Session Prompt — Email Template Integration (ET)

Operating mode: DETAIL

## Session setup

Before doing any work, read `CLAUDE.md` at the repo root of `dbower44022/crmbuilder` and confirm you have read it. Follow its governance: you commit, Doug pushes via GitKraken. Never `git push`, never `rm -rf`, never `git reset --hard`.

Reference document: `CRMBuilder-PRD-EmailTemplateIntegration.docx` v1.0 (Email Template Integration (ET), implementation-level PRD). Read it in full before proposing anything. The architecture decision is already made and is not open for redesign: **EspoCRM renders templates via its parse action; CRM Builder never implements placeholder substitution (Decision ET-D1, requirement ET-112).**

## Objective

Implement the ET feature in the CRM Builder compose UI per the PRD:

1. **Template picker** — list EspoCRM email templates using the acting user's credentials so role/team visibility is honored (ET-100..103).
2. **Rendering** — on selection, call the EspoCRM EmailTemplate parse action with template id + parentType/parentId; load the returned subject/HTML body into the compose editor as an editable draft; show attachment ids as removable chips without downloading bytes yet (ET-110..114, ET-B3).
3. **Editing behaviors** — free editing; "Replace current content?" prompt when a template is selected over a non-empty draft (ET-113/ET-B1).
4. **Send** — via the acting user's Gmail auth; download retained EspoCRM attachments at send time; attachment download failure blocks the send (ET-130..132).
5. **Write-back** — after Gmail confirms, POST an Email record to EspoCRM (status Sent, parent linkage, acting-user attribution); write-back failure surfaces a retry, never silent (ET-140..143).

## Constraints and standards

- DETAIL mode: one consequential step at a time. Present your implementation plan first and wait for approval. Ask clarifying questions before writing code. Low bar for what counts as consequential.
- Minimal-change discipline: surgical edits to existing compose UI code; do not rewrite existing modules. Ask before removing any existing functionality.
- First implementation step (before UI work): verify the EspoCRM parse action signature against the CBM instance's EspoCRM version (PRD Open Issue ET-OI-4) and record the confirmed endpoint path, request payload, and response shape in the integration module's docstring.
- Failure model per PRD Section 5.3: parse failure leaves draft untouched; Gmail failure preserves draft and skips write-back; write-back failure notifies with retry.
- Tests: pytest coverage for the integration layer (parse call, attachment deferral, write-back payload, each failure path) with EspoCRM/Gmail mocked. All existing tests (1,080 passing) must remain green. Run ruff before committing.
- Commit in logical units with descriptive messages. Do not push.

## Suggested step sequence (propose your own if better, then wait for approval)

1. Read PRD + relevant existing compose/Gmail/Espo client modules; present plan.
2. Verify parse action signature against CBM instance (ET-OI-4); document.
3. Espo client methods: list templates (acting user), parse template, download attachment, create Email record.
4. Compose UI: template picker + replace-content prompt.
5. Insert rendered draft + attachment chips.
6. Send path: attachment download, MIME assembly, Gmail send.
7. Write-back + retry UX.
8. Tests + ruff; final review summary of all changes.

## Acceptance

Walk through PRD Section 7 (AC-1 through AC-8) at the end and state pass/fail/not-testable-locally for each.

## End of session

State what was committed, what remains from the PRD (including open issues ET-OI-1..4 status), and draft the next session prompt.
