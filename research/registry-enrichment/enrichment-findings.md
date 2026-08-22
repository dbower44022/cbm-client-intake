# Enrichment Characterization Pass — Findings

**Status: complete. All 201 of 201 records attempted and scored.**

---

## Headline

| Measure | Pool-weighted estimate |
|---|---|
| **Strong-match rate** | **2.03%** |
| **False-positive rate** | **96.94%** |

Pool weights are `0.0484·A + 0.2659·B + 0.6857·C` per §6b. No unweighted aggregate appears anywhere
in this report.

**Question 2 — the one that decides the architecture — is answered decisively.** Of the 147 records
where a plausible candidate surfaced, **141 failed verification.** A pipeline scoring only "did we
find a website" would have reported ~73% success against a real strong-match rate of 2%. The prior
four-record hand-sample was not unlucky; it was representative.

**The usable rate is lower still.** Of the 6 records scoring `3`, only **2** yield actionable new
contact information for a business that is plausibly a mentoring prospect in the service area —
about **1.1% pool-weighted**. See [Strong matches](#strong-matches), which is the section that
should drive the PRD decision rather than the headline.

---

## By bucket

| Bucket | Pool | Pool share | Sampled | Scored | Strong (3) | **Strong rate** | `candidate_found=yes` | Failed verification | **False-positive rate** | Score 0 / 1 / 2 / 3 |
|---|---|---|---|---|---|---|---|---|---|---|
| `A_generic` | 73 | 0.0484 | 67 | 67 | 3 | **0.0448** | 57 | 54 | **0.9474** | 61 / 2 / 1 / 3 |
| `B_mixed` | 401 | 0.2659 | 67 | 67 | 2 | **0.0299** | 51 | 49 | **0.9608** | 63 / 2 / 0 / 2 |
| `C_distinctive` | 1,034 | 0.6857 | 67 | 67 | 1 | **0.0149** | 39 | 38 | **0.9744** | 66 / 0 / 0 / 1 |
| **Total** | **1,508** | | **201** | **201** | **6** | | **147** | **141** | | 190 / 4 / 1 / 6 |

False-positive rate is `(candidate_found=yes AND match_score<3) ÷ (candidate_found=yes)`.

`candidate_found=no` on 54 of 201 (26.9%) — nothing plausibly related surfaced at all.

### Does distinctiveness help? No — it hurts, monotonically

This is the most useful secondary finding, and it inverts the assumption behind the stratification.

| | `A_generic` | `B_mixed` | `C_distinctive` |
|---|---|---|---|
| Strong-match rate | 4.48% | 2.99% | **1.49%** |
| False-positive rate | 94.74% | 96.08% | **97.44%** |
| `candidate_found=yes` | 85% | 76% | **58%** |

Strong-match rate **falls** as names get more distinctive, and it falls by 3× across the range.
The mechanism is visible in the record notes:

- **A generic name sometimes collides with something real and related.** Two of the three `A`
  strong matches were found through a *parent company* or the owner's *prior business* — findable
  precisely because generic-named entities are often subsidiaries or rebrands of established firms.
- **A distinctive name usually collides with nothing at all.** `C_distinctive` has the lowest
  `candidate_found` rate (58%) because coined tokens — `Chayadore`, `Sprett`, `Cavsyl`, `Wedeux`,
  `Hydrohustle`, `BDLV17`, `SMGTC`, `FASW`, `QHR`, `D1HOMES` — return literally nothing. A
  brand-new microbusiness with a coined name has no web presence to find.
- **Distinctiveness does not protect against collision, it just relocates it.** The single most
  distinctive name in the sample, `KODOK STUDIO LLC`, matched Kodok Creative Studios of **Sharjah,
  United Arab Emirates**. The collision space is global, not local.

**Implication:** the 67/67/67 stratification was designed around a hypothesis that the data
contradicts. A rerun should not spend disproportionate effort on generic names expecting a worse
rate there — the worse rate is in `C`, which is also 68.6% of the pool.

---

## Channel mix

Across the 7 records scoring `>= 2`:

| Channel | Count |
|---|---|
| `own_domain` | 3 |
| `directory` | 3 |
| `facebook` | 1 |
| `instagram` / `linkedin` / `phone_only` / `none` | 0 |

Two structural biases make this mix unrepresentative rather than merely small:

1. **Social channels are capped by the method, not by reality.** Facebook and Instagram serve no
   address, ZIP, phone or owner name to automated fetch — Instagram returns base64 image data. Since
   §3 requires page-level evidence, a social-only match can essentially never reach `3`. Three of
   the four records scoring `1` are social-channel matches that stalled for exactly this reason
   (`MM CONSTRUCTION SOLUTIONS`, `B&C AUTO REPAIR`, `THE REIGN HAIR SALON`), and the single `2`
   (`L AND M CONSTRUCTION OF OHIO`) is a Facebook match capped at metro level for the same reason.
2. **BBB profiles fetch reliably and were the most productive single source** — 3 of the 6 strong
   matches. Worth prioritising explicitly in a rerun.

---

## Strong matches

All 6 records scoring `3`, with the evidence each rests on. **None rests on `agent_addr` alone.**

| Doc | Business | Bucket | Channel | Evidence |
|---|---|---|---|---|
| 202615305754 | FRESHCHOPZ LLC | C | `own_domain` | Own site names founder "Bukunmi" / Oluwabukunmi Araba — the sole associate — in its About content; phone 216-220-7039 |
| 202616805524 | POWER HOME SERVICES LLC | A | `directory` | BBB profile shows `Westlake, OH 44145` (= filing_zip) **and** lists `Robert Power` as contact (= sole associate); phone (216) 409-6541 |
| 202615902378 | ROYAL HOME & LAWN LLC | B | `directory` | BBB profile lists `Mr. Scott Grimes, Owner` = the sole associate; phone (513) 446-4949 |
| 202616603590 | CLEVELAND SUPERIOR TIC LLC | A | `own_domain` | `6110 Parkland Blvd, Cleveland, Ohio 44124` = filing_addr + filing_zip exactly, on Industrial Commercial Properties' page; phone 440-539-1046 |
| 202617502104 | NEW ALBANY VETERANS COMPANY, LLC | B | `own_domain` | `Carnegie Management and Development Corporation` (= sole associate) at `27500 Detroit Rd. Westlake, OH 44145` = filing_addr + ZIP; phone 1.440.892.6800 |
| 202615601930 | REED TRANSPORTATION SOLUTIONS LLC | A | `directory` | `35866 SPATTERDOCK LN SOLON, OH 44139-5096` = filing_addr + filing_zip exactly; exact entity name; USDOT 6146508 |

### Only 1 of 6 is the business's own findable presence

**This is the finding that should drive the decision, and it is invisible in the rate.** Classifying
the six by *what was actually found*:

| Class | Count | Records | What a mentor would actually receive |
|---|---|---|---|
| **Entity's own presence** | **1** | FreshChopz | The business's own domain, its own name, its owner named on it, and a working Cleveland phone number. This is what enrichment is supposed to produce. |
| **Owner's prior / parallel business** | 2 | Power Home Services, Royal Home & Lawn | A real, working phone number for the right human, found under a different trading name. Genuinely useful. |
| **Affiliate / parent presence** | 2 | Cleveland Superior TIC, New Albany Veterans | A commercial developer's switchboard. Correct contact route, but both are single-purpose real-estate vehicles (a tenancy-in-common and a VA build-to-suit) that will never want a mentor. |
| **Registry echo** | 1 | Reed Transportation | A trucking directory page scraped from the FMCSA carrier registry. No phone, no email, no owner name, and the address is identical to the SOS filing. Adds **zero** contact reach over data already held. |

Subtracting the two SPEs and the registry echo leaves **3 records with actionable new contact
information**. Subtracting `ROYAL HOME & LAWN`, which is a **Dayton** business (Montgomery County —
its only Ohio address on the filing is a Cleveland commercial agent), leaves **2 of 201 that are
both actionable and in the Cuyahoga/Lake service area** — roughly **1.1% pool-weighted**.

**The rubric's 2.03% is correct as specified but overstates downstream usefulness by about 2×.**
Take the PRD decision against ~1%.

---

## False positives — worked examples

Twelve of the 141, chosen to span the distinct failure modes rather than to be proportional.

| Business (filing location) | What surfaced | Why rejected | Failure mode |
|---|---|---|---|
| BIGGS ELECTRIC LLC (Cleveland 44102) | Biggs Electric LLC — Round Rock / **Austin, TEXAS**, owner David Biggs, since 1999, licence TECL#29158, phone 512-248-BUZZ, with BBB, Houzz, Instagram and Indeed presences | Character-identical name — and this filing's owner is named **AUSTIN** Biggs, so his own first name is the Texas city, steering every combined query harder toward Texas | Exact name + owner token both point to the wrong company |
| HAULCORE LOGISTICS LLC (Lakewood 44107) | FMCSA SAFER USDOT 4419177, legal name `HAULCORE LOGISTICS` — fetched: 405 Division St, Elizabeth **NEW JERSEY**, (908) 827-1333 | Exact name in an authoritative **federal** registry, wrong company | Government registries are not immune to same-name collision |
| KOZ TRANSPORT LLC (Parma 44134) | FMCSA SAFER USDOT 4429712, legal name `KOZ TRANSPORT LLC` — fetched: 3601 Saint Joseph Pl, Hobart **INDIANA**, (219) 231-5366 | Same failure as above. 2 of the 3 exact-name SAFER matches attempted were out-of-state | Registry echo, wrong entity |
| CLEVELAND PLANT COMPANY, LLC (Cleveland 44113) | The Cleveland Plant and Flower Company (founded 1913, 112 years old, 12920 Corporate Dr, six distribution centres) **and** Cleveland Plants LLC (4736 Lorain Ave, 44102) | Right city, right trade, near-identical name — two established firms | **Highest-risk class:** correct metro + correct trade |
| CREST TRANSPORTATION AND LOGISTICS LLC (Westlake agent / Austin filer) | crestlogisticsusa.com — "Crest Transportation and Logistics LLC", Central Point **OREGON**, USDOT 2247600, (541) 973-2330 | Character-for-character the registered name, 2,300 miles away | Exact name, wrong state |
| KODOK STUDIO LLC (Westlake agent) | Kodok Creative Studios — fetched: "a registered company in Sharjah Media City, **United Arab Emirates**" | A coined, near-unique token still collided — globally | Distinctiveness is no protection |
| EXODUS 35:35 LIMITED (Shaker Hts / Bedford Hts) | EXODUS 35:35 LTD — 38 Willoughby Rd, Slough, Berkshire, **UK**, incorporated 25/11/2020, retail clothing, **dissolved 16/05/2023** | Identical name, wrong country, and defunct | Scripture-reference names collide globally |
| OHIO LENDING PARTNERS LLC (Independence 44131) | Green Lending LLC (6801 Brecksville Rd, **44131**), Nations Lending (4 Summit Park Dr, **44131**), Liberty Home Mortgage (6225 Oaktree Blvd, **44131**) | Right trade, right city, **right ZIP** — all wrong companies; 6300 Rockside Rd is multi-tenant | Correct ZIP, wrong entity |
| BOSS UP LAWN CARE & SNOW REMOVAL LLC (Painesville 44077) | Aaron's Lawn Care and Snow Removal LLC — a real 15-year Ohio business in Olmsted Falls, identical trade | This filing's owner is **Aaron** Williams. Right first name, right trade, right state, wrong city | Owner first name + trade both match the wrong firm |
| LA UNION MEMPHIS CORP. (Cleveland 44144) | Waze directions for S Cleveland St & Union Ave in **Memphis TN**, historic Union Avenue postcards, Memphis magazine archives | Zero business results of any kind. The entity is named for its street (5517 Memphis Ave) and Memphis TN also has a Cleveland Street | Total geographic collapse |
| ORANGUTAN WINDOW CLEANING, LLC (Beachwood 44122) | YouTube / TikTok / Dailymotion clips of zoo orangutans washing windows with squeegees | The business is named after an animal famous online for doing exactly this activity | Name matches viral non-business content |
| YS CONSULTING GROUP LLC (Mentor 44060) | Owner **confirmed** in Mentor OH 44060; also ysconsulting.llc — fetched: Houston TX phone (713) 252-7789 | Business-level candidate contradicted. Owner located, but she is an employee of an unrelated mortgage firm and no source names the LLC | Owner found, entity not |

**The owner-found-entity-not trap deserves naming separately.** It occurred on 6 records and is the
most seductive failure mode, because the *person* is often highly findable while the *business* is
not. The clearest case: `BAILEY PROFESSIONAL AND ACADEMIC SERVICES, LLC`, where Dr. Donisha Bailey
was identified completely — Director of Exceptional Children for Euclid City Schools, previously
Principal of Shoreview Elementary, doctorate from Walden — right person, right city, exactly the
right field. Every source was an employer profile or local news. Scoring that a hit would mean
handing a mentor a school district's phone number.

---

## Method notes

Everything here would change a rerun.

### Cost — the prompt's budget was 3× too high

| | Prompt estimate (§3) | Actual |
|---|---|---|
| Searches | ~600 | **392** (mean 1.95 per record; 35 records took 1, 141 took 2, 25 took 3) |
| Page fetches | "comparable number" | **~45** |

Query cost came in well under estimate because step 2 was skipped where step 1 already surfaced a
candidate worth verifying, and step 3 was skipped where the entity name implied no trade. Fetches
were far below estimate because most records never produced a candidate worth opening.

**But the run still could not complete in one session.** The default
`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` ceiling is 200, which stopped the first attempt at
record 90; it was raised to 700 and the pass finished in a second session. **A rerun needs the
ceiling set to ~450 before starting.**

### Page fetching, not search, is the binding quality constraint

Fetching is not budget-limited but fails often, and §3's requirement that verification rest on a
fetched page means every fetch failure caps a score. Observed blockers:

- **HTTP 403** — icpllc.com, homeadvisor.com, curbsidesos.com, angi.com, bandcautorepair.com
- **Dead domains that search still indexes** — `greatlakespowerwashoh.com`, `amhomessolution.com`,
  `behindthesocial.net` all appeared in results but returned DNS `ENOTFOUND`. A distinct and common
  failure: the search index outlives the small business's domain.
- **404 across an entire site** — every `jgmoving.com` URL
- **TLS failure** — `conexuspartners.com`
- **JS shells** — Facebook returns a business name and nothing else; Instagram returns base64 images
- **Truncated content** — ibislegacylaw.com, and one Facebook page

Three records are tagged `FETCH_BLOCKED` in `notes` and scored `1`; all three would plausibly have
scored `2`–`3` on a successful fetch. **A rerun with a real browser (or accepting Google Business /
Maps as a source) would likely raise the strong-match rate materially. Read 2.03% as a floor.**

### State licensing registries are the highest-value unexploited source

Four records (`ALIGN DRIVING SCHOOL`, `BRAZILS LITTLE WORLD LEARNING AND FAITH ACADEMY`,
`GENESIS EARLY LEARNING`, and by extension the HVAC/contractor/trucking records) are in
**state-licensed trades** where an authoritative registry would settle the question and free web
search structurally cannot. The Ohio DPS licensed-driving-school registry
(`apps.dps.ohio.gov/DETS/public/schools`) surfaced in results but was not queryable as a database.
Childcare is licensed by the Ohio Department of Education and Workforce; contractors are registered
municipally (Euclid, Broadview Heights, North Royalton and Brecksville registries all appeared in
results). **Recommend: for regulated trades, query the licensing registry directly instead of
general web search.**

### Query patterns

- **Worked:** exact-phrase name + `agent_city` + `Ohio` (step 1) is the highest-yield single query.
  Appending the primary associate's surname to the unquoted step-2 query was consistently more
  discriminating than the bare `{business_name} Ohio` template and often folded step 3 in for free;
  `queries_used` records verbatim what was run per record.
- **Failed:** step 3 as templated is useless when the primary associate has a common name
  (`James Brown`, `Christopher Williams`, `Rick Smith`, `Susan Beth Smith`, `Mohammed Ali` — all
  returned nothing usable). The spec's "first entry in `associates`" rule sometimes picks the
  *worse* name: on doc 202616605274 it selects `RICK SMITH` when the second associate
  `MARK R. ERNY` was the discriminating one. **Recommend: choose the rarest associate name, not the
  first.**
- **Systematic collisions to expect.** These wrecked whole result sets:
  - *Owner surname is also a place name:* `Durham` → Durham NC (total collapse); `Hudson` → Hudson
    OH; `Austin` Biggs → Austin TX; `Christian Mason` → Mason OH; `Houston` Tucker → Houston TX;
    `Alexandria` Ledger → Alexandria OH; `Greer` → Greer SC; `Holmes` → Holmes County OH
  - *Entity name contains a street that is a city:* `Memphis`, `Lorain`, `Euclid`, `Lee`
  - *Same-named city elsewhere:* Cleveland **TN** and Cleveland **MS** both absorbed queries
    (docs 202616904474, 202614706088, 202615202968)
  - *Owner surname is an industry term:* `Elder` → elder care; `Witcher` → The Witcher game
  - *Name matches media:* `The Oxcart` + owner surname `Krause` → the novel *The Oxcart Trail* by
    Herbert **Krause**; `Danskyes Afterlife Attic` → *Afterlife in the Attic*, a cozy mystery
  - *Name is an industry term:* `Structured Cabling & Wiring`, `Fleet Performance Management`,
    `Northern Ohio Fuel & Retail`, `Offsite Construction Service`
  - *Coined blend silently normalised:* `Remedical` → "medical transport"; `Hydrohustle` → "hydro"
  - *Apostrophes and unusual spellings normalised away:* `Je'Von Smith` → Jeremiah Smith (Ohio
    State football), which erased the query entirely
- **Aggregator noise:** directory *category* pages (Angi, LawnStarter, Thumbtack, Yelp city lists,
  GreenPal, BBB category) dominate low-signal result sets and are not candidates. See rule 1 below.
- **Dangerous noise:** two records returned criminal-record or obituary hits on a same-named person
  (docs 202616801512, 202617003068, 202615500752, 202615902778). These must never be attached to a
  business record.

### Scoring rules adopted where the rubric needed interpretation

Recorded so a rerun reproduces the same numbers, not merely the same method.

1. **`candidate_found=yes` requires a *named business* that is name-confusable with the entity — a
   shared rare token or near-name — or a business matching trade + area + owner signal.** Bare
   directory category pages are not candidates. Without this rule every record is trivially `yes`
   and the false-positive denominator stops meaning anything. *Boundary caveat:* "rare token" is a
   judgment call (`Papik` and `Zenith` counted; `Global`, `Ruby` and `Polaris` did not).
   `candidate_found` is the softer of the two fields; `match_score` is the robust one.
2. **An owner's separate business is not an online presence for this entity.** Applied to 6
   owner-found-entity-not records, all scored `0`. Applied in the *other* direction where the
   trading name shares the entity's distinctive token and the address matches
   (`POWER HOME SERVICES` → Power Professional Services, scored `3`).
3. **A bare name-token match in a saturated namespace is not "probably right"**, so it scores `0`
   rather than `1`. `ELITE CONSTRUCTION CO, LLC` competes with nine same-token Ohio firms → `0`;
   `MM CONSTRUCTION SOLUTIONS LLC` had a Facebook handle matching the *full* distinctive entity
   name → `1`.
4. **Commercial aggregators and people-search sites are not accepted as verification sources** —
   ZoomInfo, Dun & Bradstreet, RocketReach, Spokeo, OfficialUSA, Radaris, Veripages, ContactOut,
   DeepEnrich, Seamless.AI, InstantCheckmate. Excluded under the §7 free-web-search guardrail. They
   appeared frequently and would have closed several records; **this exclusion suppresses the
   measured rate by an unknown amount** and is the single most likely source of downward bias.
5. **Professional intermediaries acting as agent/associate score `0`.** Fifteen records have a law
   firm, accountancy or corporate-services shell as statutory agent and often as sole associate.
   The starkest is doc 202614802682 (`CEDAR AND LLOYD, LLC`), where the associate **Ibis Legacy
   Law, LLC** is verifiably at `20133 Farnsleigh Rd, Shaker Heights, OH 44122` — this filing's
   exact filing_addr, matching ZIP, and the associate's own name on the source. **All three §4b
   score-3 criteria are literally satisfied, and it is still scored `0`**, because contacting an
   estate-planning firm reaches counsel, not a business. Answering the measurement question
   honestly requires this. *Sensitivity: scoring these five clearest cases as `3` would roughly
   double the headline rate while adding zero usable contacts.* No score `3` in this run rests on
   `agent_addr` alone.

### Data-quality observations on the input — the highest-leverage change available

- **Roughly 37 of 201 records (18%) have no genuine local address at all.** Both their agent and
  filer addresses are formation-service mail drops. Recurring signatures:
  - `Republic Registered Agent, 850 Euclid Ave` + associate **LOVETTE DOBSON** + filer
    `134 Vintage Park Blvd A-50, Houston` — **13 records**, spanning cleaning, trucking, title
    insurance, auto sales, construction, landscaping, design and consulting. One person, thirteen
    unrelated "businesses." These are almost certainly not operating companies.
  - `United States Corporation Agents, 1991 Crocker Rd` + filer `11501 Domain Dr, Austin TX` — 12+
  - `Entity Protect, 815 Superior Ave` + filer `420 Lexington Ave, NYC` — 8+
  - `Legalinc Corporate Services` + filer `10601 Clarence Dr, Frisco TX` — 2
- **Six pairs/families of records share an address or intermediary**, including three EREI entities
  (a parent and two numbered subsidiaries), the `ROF TA [city]` series, and attorney Mark Shearer's
  Strongsville office appearing on three separate records.
- **Filtering commercial-agent-only filings out of the qualified pool before enrichment is the
  single highest-leverage change**, on two counts: it removes ~18% of records that are structurally
  unmatchable, and those records are not mentoring prospects anyway.
- **The sample's geographic premise does not hold for every row.** Two of the six strong matches
  resolved to businesses outside Cuyahoga/Lake (`ROYAL HOME & LAWN` in Dayton) or named for another
  county entirely (`GEAUGA COMPUTER RECYCLING`). Records whose only Ohio address is a commercial
  agent cannot be assumed to be local businesses.
- **Field integrity defects:** doc 202616605274 has an **email address** in `agent_name`; doc
  202616103938 has an email as a second `associates` entry; doc 202615405558 lists the formation
  service `USA LLC FILING` as an *associate*; doc 202615511288 has a filing address with no street
  name (`26351, EUCLID 44132`); doc 202616205160 has a malformed 9-digit ZIP (`441225712`); doc
  202617306950 abbreviates the city to `CLEV`; doc 202616303550 misspells `CONTINENAL`; doc
  202614904546 is registered as `SOUTHER OHIO TRANSPORT` (a typo of SOUTHERN) which actively
  defeats exact-phrase search.
- **Bucket assignment is unreliable in places.** `WEDEUX DESIGN COMPANY LLC` and
  `GREAT LAKES BOTANICAL LLC` are labelled `A_generic` despite coined or highly specific names.
  Since the pool weights and the whole stratification rest on this classifier, and since the
  bucket-level rates now differ by 3×, **the classifier is worth auditing before these numbers are
  relied on.**

---

## What this means for the PRD decision

Stated plainly, because the numbers are unambiguous:

1. **Free-web-search enrichment of newly formed Ohio registrations does not work at a useful rate.**
   2.03% pool-weighted strong-match; ~1.1% actionable and in-area. On a pool of 1,508 that is
   roughly 16 usable contacts for ~2,900 searches and ~340 page fetches.
2. **The false-positive rate is the real risk, and it is 96.94%.** Any pipeline that does not
   implement verification-with-corroboration as a separate scored step from candidate-discovery
   will attach wrong contact details ~19 times out of 20. §4's two-field design is not optional.
3. **Two cheap changes would improve the economics more than better search would:** filter
   commercial-agent-only filings out of the pool (~18% of records, structurally unmatchable, not
   prospects), and query state licensing registries directly for regulated trades.
4. **A paid-API comparison is now worth running.** §7 said it was worth it "only if this pass shows
   a nonzero-but-low rate." That is exactly what it shows. Note also that exclusion rule 4 above
   means this pass deliberately declined data that commercial aggregators had — so a paid comparison
   is measuring a real difference, not just a budget difference.

---

## Revision control

| Field | Value |
|---|---|
| Document | Enrichment Characterization Pass — Findings |
| Version | v1.0 |
| Last Updated | 07-30-26 03:05 |
| Prepared by | Claude, for D. Bower |
| Status | Complete — 201 of 201 records scored |
| Source prompt | `claude-code-prompt-enrichment-characterization-v0.2.md` |
| Scored data | `enrichment-sample-201-scored.csv` (201 rows, 201 scored, 0 blank) |

### Change log

| Version | Date | Change |
|---|---|---|
| v0.1 | 07-30-26 02:15 | Partial findings, 90 of 201. Pool-weighted estimate withheld as not computable — `C_distinctive` was 0-of-67 and carries 0.6857 of pool weight. Per-bucket rates for A (census-grade) and B (provisional) only. |
| v1.0 | 07-30-26 03:05 | **Complete: 201 of 201.** Pool-weighted strong-match 2.03%, false-positive 96.94%. Adds the finished `C_distinctive` bucket, which reverses the distinctiveness hypothesis — strong-match rate declines monotonically with distinctiveness (A 4.48% → B 2.99% → C 1.49%), because coined names collide with nothing while generic names sometimes collide with a findable parent or predecessor. Adds the actionable-contact breakdown: only 1 of 6 strong matches is the entity's own presence and only 2 of 201 are actionable and in-area (~1.1%). Adds two exact-name FMCSA registry false positives (HaulCore → New Jersey, KOZ Transport → Indiana), refuting the assumption that federal registries are collision-proof. Quantifies the serial-filer problem at ~18% of the sample, with one associate accounting for 13 records. Records five interpretation rules and their sensitivity, including the Ibis Legacy Law case where all three §4b score-3 criteria are literally met and the record is still scored 0. Adds the state-licensing-registry recommendation. Corrects the cost estimate downward: 392 searches actual vs ~600 budgeted. |

### Acceptance criteria status

| Criterion | Status |
|---|---|
| All 201 rows carry `candidate_found` and `match_score` | **Met** — 201/201, no shortfall |
| `candidate_found` judged independently; `yes` with score `0` expected | **Met** — 141 of 147 `yes` records scored `<3`; that is the finding |
| Every `match_score >= 2` has `evidence` and a taxonomy `found_channel` | **Met** — 7 of 7; no record below `2` has a channel set |
| No `match_score = 3` rests on `agent_addr` alone unless `agent_name` matches an associate | **Met** — verified per record; caveat additionally applied in spirit to 15 professional-intermediary records |
| `queries_used` populated for every row | **Met** — 201/201 |
| Per-bucket rates **and** a pool-weighted estimate; no unweighted aggregate | **Met** — both reported; **no unweighted aggregate appears** |
| False-positive rate as `(candidate_found=yes AND match_score<3) ÷ (candidate_found=yes)` | **Met** — 141 ÷ 147 |
| Both outputs under `research/registry-enrichment/`; nothing written to the CRM | **Met** — nothing written to the CRM; no reusable modules built; scratch scripts not committed |
| No re-sampling, re-sorting or dropped rows | **Met** — row order and all 201 input rows unchanged |
