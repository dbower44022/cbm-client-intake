# Kickoff prompt — walk the prospect marketing process, source by source

**Written 2026-09-02. For a fresh Claude Code session rooted in
`cbm-client-intake`.** This is a discussion session, not a build session. Its
purpose is to find out whether the funnel needs more status buckets than the
drafts on the table, by walking the actual process end to end for each source.

---

## The prompt

We are designing a marketing process that takes prospects from **every source**
and moves them through **one funnel** into CBM's existing intake forms. The
state of that design is in **`prds/prospect-marketing-plan.md`**, whose final
section, *Discussion in progress — funnel stages (2026-09-01)*, is where the
last session stopped. Your job this session is to **continue that discussion
with Doug**, one item at a time, and record what comes out of it. You are not
building anything and you are not deciding anything on your own.

### Read first

1. This repo's `CLAUDE.md` in full.
2. `prds/prospect-marketing-plan.md` — all of it, and the last section twice.
   Note the difference between the three kinds of content in it: **Doug's
   rulings** (2026-08-11, settled), **working positions** (2026-09-01, things
   Doug said in discussion, not yet final), and **ideas on the table** (mine,
   not adopted).
3. `research/registry-enrichment/enrichment-findings.md` §*Headline*, §*Strong
   matches* and §*Data-quality observations* — the measured reason postcards
   are the primary channel and why 18% of filings are not prospects at all.
4. `prds/events/CBM_Events_Registration_Recognition_Plan.md` §*The rule that
   shapes all of it* — the 2026-08-17 ruling that a public page may echo
   nothing we know about a person. It bears on the postcard landing page and
   has not been reconciled with it.
5. `cinformation-request-entity.md` and `forms/info_request/orchestrator.py`
   lines 130–140 — how the `source` field is written today, because the funnel's
   channel vocabulary lands there.

### What is settled, what is not

**Settled (do not reopen):** the eight 2026-08-11 rulings — an outside process
filters the raw pool; Lob or PostGrid; a per-prospect QR code to a personalized
page; two buttons into the standard forms carrying the prospect id; the same
workflow from there; a tracked source; single source of truth; Contact/Company
pollution weighed equally.

**Working positions (Doug's words, may be revised):** every source uses the
same stages; the funnel ends at the form submission and *Client* is read from
the engagement; the four-rung draft was not granular enough; a prospect with no
email, phone or business type is not as qualified as one with all three;
campaign membership must be a first-class, reportable label.

**Open, and the point of this session:** whether the process needs more status
buckets than the eight-rung Draft B; the naming family; whether "reach level" is
the right second axis; the one-record-two-halves question. Behind those, still
queued: the `source` ruling, `CProspect` storage, and the landing-page-versus-
harvester tension.

### How to run the session

Doug wants a **conversation**, not a document review. The rules, learned the
hard way:

- **One question per turn**, in prose, with your recommendation and the reason
  before it. No option menus, no bulleted lists of issues, no stacked
  `AskUserQuestion` calls.
- **Executive register.** Short paragraphs, plain words, no mechanics. Say what
  a stage *means* and what *evidence* puts a prospect there; leave field names
  and entity names out unless he asks.
- **Verify a premise before asking about it.** If a question depends on how
  the app or CRM behaves today, read the code or query crm-test first.
- **Record what he says as his; record what you think as yours.** Nothing
  becomes a ruling unless he states it as one.

The method for finding missing buckets is to **walk each source end to end**
and ask, at every step, *what just happened, what proves it, who acts next, and
which campaign or side exit does this prospect now belong to*. A bucket is
missing wherever two prospects that need different handling would carry the
same label, and a bucket is spurious wherever no one would ever act
differently because of it. Sources to walk, roughly in order of how far up the
funnel they enter:

1. State new-business filings (the postcard case) — enters at the top with
   an address and nothing else.
2. Purchased or partner-supplied lists — may arrive with an email already.
3. Webinar registrants and attendees — enter part-way down, person known,
   business often not; attendance is a second signal after registration.
4. Inbound info@ email — a person wrote to us; today captured as a held
   submission in `/ops`.
5. Partner referrals — a partner names someone; today only recorded once the
   person has already filled in a form.
6. Mentor and client referrals, and walk-ups at events — a conversation
   happened before any record exists.
7. Former or dormant clients being re-marketed — enter with everything known
   and a history.

For each, note the entry rung, every rung it can pass through, the touches
that would be made, the evidence for each move, and the side exits it can take.
Where the walk shows Draft B collapsing two states that need different
handling, propose the extra bucket **then**, in that turn, and ask.

Watch for the second axis while you walk: an enrichment hit, a landing-page
correction or a conversation can add an email or a phone without the prospect
moving a stage. Every time that happens, ask whether it changes which campaign
they belong to. That is the test of whether "reach level" is the right idea.

### Guardrails

- **No code, no CRM changes, no vendor accounts.** If the discussion produces a
  build decision, it goes in the plan as a ruling with the date; the build is a
  later session.
- **The postcard landing page shows what is printed on the card.** Anything
  beyond that collides with the 2026-08-17 harvester ruling. Raise it once when
  the walk reaches the QR scan; do not design around it silently.
- **Chapter-network vocabulary.** "Ohio SOS document number" and "State New
  Business Filing" are Cleveland-specific. A stage or source name that would
  have to change for a second chapter is a smell — note it, do not fix it.
- **Do not narrow the process to postcards.** Postcards are one campaign in a
  process that must carry every source above.

### At the end of the session

Update `prds/prospect-marketing-plan.md`'s *Discussion in progress* section
(or add a dated sibling section) with what came out: any new rulings Doug
stated, the revised working positions, the stage ladder as it stands, the
per-source walk in a compact table, and what is still open. Keep the three
kinds of content labelled as they are now. Bump the draft version. **Commit;
do not push** — Doug reviews and pushes. If the session reaches a point where
the next step is a CRM handoff or a build plan, say so and stop; write the
kickoff prompt for it as `prompts/prospect-marketing-<topic>-prompt-v0.1.md`.
