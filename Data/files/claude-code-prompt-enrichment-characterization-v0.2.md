# Claude Code Prompt — Enrichment Characterization Pass

**Deliverable:** a completed scoring CSV and a findings report answering two questions — *how often can a newly formed Ohio business be matched to online contact information, and how often does a plausible-looking match turn out to be the wrong business?*

This is a measurement exercise, not a build. **Do not build reusable modules. Do not write to the CRM.** Any throwaway script is scratch work; only the two output files matter.

---

## 1. Objective

For a fixed sample of 201 businesses formed in Cuyahoga and Lake counties in June 2026, establish:

1. **Strong-match rate** — the share matched to an online presence with corroborating evidence that it is the correct entity.
2. **False-positive rate** — of records where a plausible candidate surfaced, the share that failed verification.
3. Whether either rate varies with business-name distinctiveness.

**Question 2 is the one that decides the architecture.** A prior hand-sample of four records surfaced a plausible-looking result for every one and the correct entity for none. A pipeline scoring only "did we find a website" would have reported total success while attaching a Michigan company's phone number to a Maple Heights power washer. This pass exists to measure that failure mode, not to maximise hits.

---

## 2. Input

`enrichment-sample-201.csv` — 201 rows, fixed seed 2026, drawn from a qualified pool of 1,508.

| Column | Meaning |
|---|---|
| `doc_number` | Ohio SOS document number — stable key |
| `business_name` | Registered entity name |
| `name_bucket` | `A_generic` / `B_mixed` / `C_distinctive` — 67 each |
| `agent_name` | Statutory agent's name — needed to judge whether the agent is a commercial service |
| `agent_addr`, `agent_city`, `agent_zip` | Agent address — the better location proxy |
| `filing_addr`, `filing_city`, `filing_zip` | Filer's address — often the organiser's home |
| `associates` | Named individuals on the filing |
| `effective_date` | Formation date |

Columns to fill: `candidate_found`, `match_score`, `found_channel`, `found_url`, `evidence`, `queries_used`, `notes`.

Do not re-sample, re-sort, or drop rows. All 201 are attempted; misses are recorded as misses.

---

## 3. Method, per record

Run up to three searches, stopping early only on a score of `3`:

1. `"{business_name}" {agent_city} Ohio` — exact phrase
2. `{business_name} Ohio` — **no quotes**, only if step 1 returns nothing usable
3. `{primary associate} {agent_city} {inferred trade}` — only if 1 and 2 fail *and* the entity name implies a trade

**Parsing `primary associate`:** take the first entry in `associates`; strip role labels (`AUTHORIZED REPRESENTATIVE`, `REGISTERED AGENT`, `SOLE MEMBER`, `MEMBER`, `INCORPORATOR`); skip step 3 entirely if the result is an email address, the company's own name, or empty.

Write every query attempted into `queries_used`, pipe-separated.

**Verification requires fetching the candidate page.** A search snippet is not sufficient evidence. Open the page and look for the filing's own data. Budget accordingly: roughly 600 searches plus a comparable number of page fetches. Fetching is the slow part.

---

## 4. Scoring — two independent fields

The two fields answer different questions and must not be conflated. This was the central defect in v0.1.

### 4a. `candidate_found` — did anything plausible surface?

`yes` if any result looked like it could be this business — matching or near-matching name, or the right trade in the right area. `no` if nothing plausibly related appeared at all.

**Judged before and independently of verification.** All four hand-sample records below are `candidate_found = yes`, because candidates did surface. They then failed verification and score `0`. This is what makes the false-positive rate computable.

### 4b. `match_score` — did it verify?

| Score | Label | Criteria |
|---|---|---|
| `0` | none | No candidate, **or** a candidate that failed verification |
| `1` | ambiguous | Candidate is probably right but nothing corroborates it and nothing contradicts it |
| `2` | weak | Metro-level corroboration only — right city or county, nothing more specific |
| `3` | strong | `filing_addr`, either ZIP, or an `associates` name appears on the source |

**Only `3` counts as a hit.**

**Agent-address caveat:** `agent_addr` appearing on a source is **not** sufficient for `3` on its own. Commercial statutory agents host hundreds of entities, so their address corroborates nothing. It counts toward `3` only when `agent_name` matches an entry in `associates` — i.e. the owner is their own agent. Otherwise cap at `2`.

### 4c. Worked examples

All four are `candidate_found = yes`, `match_score = 0`:

| Business | What surfaced | Why rejected |
|---|---|---|
| Great Lakes Power Wash LLC (Maple Heights) | Companies in Detroit, Tecumseh MI, Clarkston MI, Columbus | Same name, different businesses, none in Cuyahoga |
| CLE K9 Athletic Club LLC (Lakewood) | Off Leash K9, Boss K9 | Competitors, not the entity |
| Keyz Street Kitchen LLC (Cleveland) | Cleveland Kitchen, Kennedy's Kitchen, a Texas restaurant | Name-similar, unrelated |
| Bailey K. Bookkeeping LLC (Cleveland) | Bailey Bookkeeping, Bailey's Bookkeeping Services | Unrelated firms sharing a surname |

When torn between two scores, take the lower. The expensive error is a wrong phone number reaching a mentor, not a missed lead.

---

## 5. Channel taxonomy

`found_channel` takes exactly one value, and only when `match_score >= 2`:

`own_domain` · `facebook` · `instagram` · `linkedin` · `directory` (Yelp, BBB, Google Business) · `phone_only` · `none`

The distinction is load-bearing downstream: an own domain implies a contact form and probably an email; a social page is reachable but not emailable; a directory listing may carry a phone and nothing else.

---

## 6. Output

### 6a. `enrichment-sample-201-scored.csv`

Input columns unchanged, blanks filled. `evidence` holds the specific corroborating detail, quoted briefly — `ZIP 44107 on contact page`, `owner name M. Maher in About section`. Populated whenever `match_score >= 2`.

**Write after every record.** Resumable by skipping rows where `match_score` is already populated.

### 6b. `enrichment-findings.md`

**Reporting rule — do not report an unweighted aggregate.** The sample is stratified 67/67/67, but the pool is not:

| Bucket | Pool | Share | Sampled |
|---|---|---|---|
| `A_generic` | 73 | 0.0484 | 67 |
| `B_mixed` | 401 | 0.2659 | 67 |
| `C_distinctive` | 1,034 | 0.6857 | 67 |
| **Total** | **1,508** | | **201** |

Generic names are over-weighted roughly 7×, and bucket A at 67-of-73 is close to a census rather than a sample. A flat average across 201 records does **not** estimate the rate across 1,508 and would be read as though it did.

Report instead:

- **Per-bucket rates as primary** — strong-match and false-positive rate for each of A, B, C
- **One pool-weighted estimate** — `0.0484·A + 0.2659·B + 0.6857·C`, labelled as such

| Section | Content |
|---|---|
| Headline | Pool-weighted strong-match rate; pool-weighted false-positive rate |
| By bucket | Both rates per bucket, with score distribution |
| Channel mix | `found_channel` distribution where `match_score >= 2` |
| False positives | 8–10 worked examples of `candidate_found=yes, match_score=0` — what surfaced, why rejected |
| Strong matches | Every `3`, with its evidence |
| Method notes | Rate limits, query patterns that worked or failed, anything that would change a rerun |

Include a revision control block and change log. Timestamps `MM-DD-YY HH:MM`.

### 6c. Retention

Both output files are the empirical basis for a PRD decision — keep them so the number doesn't have to be re-earned with 600 searches. Commit them under `research/registry-enrichment/`. Scratch scripts are not committed.

---

## 7. Guardrails

- **Free web search only.** No paid enrichment APIs — no ZoomInfo, Apollo, Clearbit, People Data Labs. Commercial databases source from the same web and lag on new formations; a paid comparison is a separate experiment, worth running only if this pass shows a nonzero-but-low rate.
- **No cherry-picking.** All 201 attempted. Do not skip records that look unpromising.
- **Rate-limit politely.** Pause between calls; back off on throttling rather than dropping records.
- **Do not guess.** Inferring a likely website from a business name is exactly the failure being measured.
- **Report honestly.** If fewer than 201 complete, state the count and why.

---

## 8. Acceptance criteria

- [ ] All 201 rows carry both `candidate_found` and `match_score`, or the shortfall is stated with a reason
- [ ] `candidate_found` judged independently — records with `yes` and score `0` are expected and are the point
- [ ] Every `match_score >= 2` has populated `evidence` and a `found_channel` from the fixed taxonomy
- [ ] No `match_score = 3` rests on `agent_addr` alone unless `agent_name` matches an associate
- [ ] `queries_used` populated for every row
- [ ] Findings report gives per-bucket rates **and** a pool-weighted estimate; no unweighted aggregate appears
- [ ] False-positive rate computed as `(candidate_found=yes AND match_score<3) ÷ (candidate_found=yes)`
- [ ] Both outputs committed under `research/registry-enrichment/`; nothing written to the CRM

---

## Revision control

| Field | Value |
|---|---|
| Document | Claude Code Prompt — Enrichment Characterization Pass |
| Version | v0.2 |
| Last Updated | 07-29-26 11:45 |
| Prepared by | Claude, for D. Bower |
| Status | Draft — ready for execution |

### Change log

| Version | Date | Change |
|---|---|---|
| v0.1 | 07-29-26 11:13 | Initial draft. Measurement only, no build. Rubric anchored on match verification after a four-record hand-sample in which every finding was a false positive. |
| v0.2 | 07-29-26 11:45 | Review fixes. **Blocking:** split `candidate_found` from `match_score` — v0.1 scored false positives as `0`, placing them outside the denominator and rendering the false-positive rate uncomputable. **Blocking:** added pool weights and barred unweighted aggregate reporting; 67/67/67 stratification over a 73/401/1034 pool over-weights generic names ~7×. Corrected query template 2 to unquoted. Added agent-address caveat — commercial agent addresses cap at `2`. Defined `primary associate` parse rule. Added `agent_name` and `queries_used` columns. Noted verification requires page fetches, roughly doubling the call budget. Reversed retention decision: outputs now committed under `research/registry-enrichment/`. Input renamed `enrichment-sample-201.csv` to match its row count. |
