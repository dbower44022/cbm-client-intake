# Address paste-parsing — plan

Paste a whole address — `1234 Main St Suite 200, Cleveland, OH 44113` — into the
first address input and have the app split it across Street / line 2 / City /
State / ZIP, instead of the user retyping four fields from a website they
copied it off.

Status: **shipped in v0.196.0 and deployed** (2026-08-13 push, both
environments). A live pass is still owed — see `OPEN-ITEMS.md` #20. Decisions
below are Doug's, recorded 2026-08-13.

Two things changed during the build and are recorded in place below: the paste
handler reads the **clipboard** rather than the field (a `maxlength` input
truncates before any handler could see the ZIP), and event registration turned
out to have **no page to wire** — it is API-only, `frontend_dir=None`, with the
form living on the WordPress site.

## Decisions

| Question | Ruling |
|---|---|
| **Trigger** | Fire on **paste** and on **blur**, with an inline **Undo**. Never per keystroke. |
| **Engine** | **Local heuristic only** — vanilla JS, no network, no API key, no third party. No Google Places, no USPS validation. |
| **Scope** | All four surfaces: session-tool Details tabs, Mentor Admin + My Mentor Profile, Workspace Directories, and the public intake forms. |
| **Breadth** | **Address only.** Do not parse name / email / phone out of a contact block, even where those fields sit on the same form. |

Two rulings taken as working assumptions, flag if wrong:

- **Overwrite policy** — a *full* parse (street + city + state + ZIP all found)
  replaces those fields; a *partial* parse fills only the parts it found and
  leaves the rest alone. A parsed-but-empty component never blanks an existing
  value. The Undo and the change highlight are what make replacement safe; a
  strict fill-empties-only rule would mean a wrong city still has to be retyped
  by hand, which defeats the feature.
- **Public forms are not widened.** `client_intake` and `event_registration`
  collect ZIP only; `volunteer` collects Street + ZIP. City and State have no
  input, no Pydantic field and no orchestrator mapping in the intake path
  (verified: `forms/*/schemas.py`, `forms/*/orchestrator.py` write only
  `addressStreet` and `addressPostalCode`). Adding them is a Requirements-Spec
  change, out of scope here. See *Public forms* below for what the feature does
  there instead.

## The module — `frontend/shared/address-paste.js`

One shared control alongside `datetime.js` / `richtext.js` / `phone-format.js`,
self-wiring in the `busy.js` style. No build step, no dependency.

```js
window.CBMAddress = {
  parse: function (text) { /* -> null | Parsed */ },
  looksParseable: function (text) { /* -> bool */ },
  attach: function (opts) { /* -> detach() */ },
};
```

`Parsed` = `{ street, line2, city, state, postalCode, country, confidence }`
where `confidence` is `"full"` (street + city + state + ZIP) or `"partial"`.

`attach(opts)` takes the **actual input elements**, any of which may be absent:

```js
CBMAddress.attach({
  line1: el, line2: el, city: el, state: el, postalCode: el, country: el,
  anchor: el,          // where the undo/status line is inserted (default: line1's wrapper)
  onApply: fn,         // optional: host app hook, e.g. its own dirty-tracking
});
```

It owns the paste/blur listeners, the parse, the writes, the undo line and the
highlight. Hosts supply elements and nothing else.

### Parse algorithm

US-focused, applied in order — anchor on the tail (ZIP and state are the most
reliably shaped tokens) and work backwards:

1. **Normalize** — trim, collapse runs of whitespace, treat newlines as segment
   separators equivalent to commas, strip a trailing
   `USA` / `U.S.A.` / `US` / `United States` (recording it as `country`).
2. **ZIP** — `\b(\d{5})(?:[-\s](\d{4}))?\s*$` at the tail. Normalize `12345 6789`
   to `12345-6789`; keep ZIP+4 when given.
3. **State** — the token immediately before the ZIP: either a two-letter code
   validated against the 50 states + DC, or a full state name (case-insensitive
   name→code map). Normalize to the uppercase two-letter code — this is
   load-bearing, since the session tools render State as a `<select>` and an
   unnormalized `Ohio` would silently fall out on save.
4. **City** — the segment immediately before the state.
5. **Street** — everything before the city.
6. **Unit split** — peel a trailing unit designator off the street into `line2`
   when the form has a line 2: `Suite|Ste|Apt|Apartment|Unit|Rm|Room|Fl|Floor|
   Bldg|Building|Dept|#`. `PO Box` / `P.O. Box` is the street itself, never a
   unit.
7. **Leading business name** — strip the first segment only when the *following*
   segment starts with a house number (`^\d`). This is what makes a Google Maps
   copy (`Acme Widgets, 1234 Main St, Cleveland, OH 44113`) work without
   swallowing a legitimate `Attn:` line or a two-part street.
8. **Trailing noise** — drop tokens that are plainly a phone number, a URL or an
   email address.

### When it refuses (returns `null`, touches nothing)

The refusal rules matter more than the parse rules — a false positive rewrites
four fields.

- Neither a state nor a ZIP was found.
- A single segment with no comma, no newline and no ZIP — someone is just
  typing a street address normally.
- A recognizable non-US country name, or a non-US postal pattern (e.g. a UK or
  Canadian postcode shape). Leave the pasted text in line 1 verbatim.
- The blur path additionally refuses unless `looksParseable(text)` is true —
  it requires a comma, a newline, or a ZIP-shaped token.

## Interaction

The paste handler reads the **clipboard text** and computes what the field
*would* hold, rather than letting the paste land and reading the field
afterwards. That is forced by `maxlength`: the intake ZIP field is
`maxlength="10"`, so the browser truncates a pasted address to ten characters
before any handler could see the ZIP in it. A refused parse never calls
`preventDefault`, so text we don't understand still pastes normally.

On a successful parse:

1. **Snapshot** every target field's current value.
2. **Write** each parsed component through one `setValue(el, v)` helper that
   sets `.value` and then dispatches a **bubbling `input` and `change` event**.
   This is required, not cosmetic — see *Traps*.
3. **Highlight** the fields that actually changed for ~2s.
4. **Render the status line** below line 1:
   *"Filled City, State and ZIP from what you pasted. **Undo** ×"* — naming the
   fields that changed, not a generic message.
5. **Undo** restores the snapshot (dispatching the same events) and removes the
   line. The line otherwise persists until dismissed or replaced by another
   parse.

Rules the writer obeys:

- Never write to a `disabled` input (shipping, when *Same as billing* is on).
- Never write a `<select>` a value it does not offer — if the state code is not
  an option, leave state blank rather than injecting an option.
- Never blank an existing value with a parsed-but-empty component.

## Where it wires in

| # | Surface | Hook | Fields |
|---|---|---|---|
| 1 | **Session tools** — Client / Partner / Funder Management, Details tab | `addressBlock()` in `sessions/frontend/app.js` (~4255) | line1, line2, city, state (select), ZIP, country |
| 2 | **Mentor Administration** `/mentoradmin` | after the detail form renders | `addressStreet` (textarea), City, State, ZIP |
| 3 | **My Mentor Profile** `/mentorprofile` | same | same |
| 4 | **Workspace Directories** `/directory` | the `f.type === "address"` branch of `registerField` | sub-fields from the CRM layout |
| 5 | **Volunteer intake** | `forms/volunteer/frontend/app.js` | `#street`, `#zip_code` |
| 6 | **Client intake** | `forms/client_intake/frontend/app.js` | `#zip_code` only (ZIP-rescue mode) |
| — | ~~Event registration~~ | **no page exists** — `frontend_dir=None`; the form lives on the WordPress site | — |

**1 — Session tools.** The single best hook in the codebase: `addressBlock` is
invoked from three places in `DETAILS_LAYOUTS` — the **Contact** address, and
Company **billing** and **shipping** — so one `CBMAddress.attach({...})` call at
the end of the function covers all three, across all three session tools. Every
element is already in hand as a local (`a1`, `a2`, `city`, `state`, `zip`,
`country`).

**2 & 3 — Mentor screens.** Fields are flat, declared in
`mentoradmin/service.py:EDITABLE_FIELDS` and `mentorprofile/service.py:
PROFILE_FIELDS` with `row: "citystate"`, and rendered with
`dataset.field` / `dataset.type` / `dataset.original`. Wire by querying
`[data-field="addressStreet"]` and friends after render. Here `addressStreet` is
a `text` (textarea) with no separate line 2 — the unit becomes the **second line
of the textarea**, matching how the CRM stores a multi-line street.

**4 — Directory.** Address sub-fields come live from the CRM layout, so match by
**suffix** (`Street` / `City` / `State` / `PostalCode` / `Country`) rather than
exact names — the prefix varies (`address`, `billingAddress`, `shippingAddress`).
The `f.type === "address"` branch already receives the whole sub-field group,
which makes it the tidiest of the three hooks.

**5 & 6 — Public forms.** Different by necessity, because there is nowhere to
put City and State.

- **Volunteer** has Street + ZIP. A pasted full address **tidies into Street and
  fills ZIP** — the whole normalized string stays in Street (which maps to the
  CRM's multi-line `addressStreet`), so nothing the submitter typed is lost, and
  the required ZIP field stops being retyped.
- **Client intake and event registration** have a ZIP field only. This is worth
  doing for a reason beyond convenience: `#zip_code` carries
  `maxlength="10"`, so pasting a full address into it today **silently truncates
  to the first ten characters** and submits garbage. ZIP-rescue mode extracts the
  ZIP from the pasted text and discards the rest, turning a data-corruption
  footgun into the right value.
- Both need `<script src="/shared/address-paste.js"></script>` after `busy.js`.

## Traps

- **Dispatch bubbling `input` events.** `directory` binds `markChanged` with
  `addEventListener("change"/"input", …)`, and `sessions` runs the *Same as
  billing* mirror off a **delegated `input` listener on the form**
  (`sessions/frontend/app.js` ~4357). Setting `.value` alone means a paste into
  billing never mirrors to shipping, and the directory Save button never enables.
- **State is a `<select>` in the session tools** and a free `varchar` on the
  mentor screens — the same normalized `OH` must be safe for both, hence the
  validate-before-write rule.
- **Save-diffing is snapshot-based** (`dataset.original`, compared at save time
  in `mentoradmin` / `mentorprofile`). Parser writes are indistinguishable from
  typing there, which is correct — but it also means Undo must restore the
  *original string*, not merely clear the field.
- **`app.js` in the session tools is one shared IIFE** — grep any helper name
  before adding it ([[sessions-appjs-single-scope-collisions]]).
- **Don't cap the address block's width** to make the parse preview fit
  ([[no-page-width-caps-density-by-packing]]).
- **Removing the notice and forgetting the undo snapshot are different things.**
  Folding them into one helper nulled the snapshot on the way IN — `showNotice`
  clears any previous line first — so Undo rendered, clicked, and silently did
  nothing. The parse table could never have caught this; it took a real click in
  a browser. Guarded by `test_undo_survives_the_notice_being_rebuilt`.

## Tests

- **`tests/test_shared_address.py`**, mirroring `tests/test_shared_datetime.py`:
  the asset ships, is served at `/shared/address-paste.js`, exports
  `window.CBMAddress`, and every page owning an address block loads it. This is
  the wiring guard, and it is what stops a new address form shipping without it.
- **Parser correctness** runs as a real test after all. `parse()` is a pure
  function, and the Python test loads the shipped module into a `vm` context
  under **node** and asserts a 20-case table. No `package.json`, no dependency,
  no build step — and it tests the file that actually ships rather than a Python
  twin that could drift. It **skips** where there is no JS runtime (the deploy
  image has none), so the wiring guards still run everywhere.

Case table to cover, at minimum:

```
1234 Main St, Cleveland, OH 44113                     full
1234 Main St Suite 200, Cleveland, OH 44113           full, line2 = "Suite 200"
1234 Main St\nCleveland, OH 44113                     full (multi-line paste)
Acme Widgets, 1234 Main St, Cleveland, OH 44113       full, business name dropped
1234 Main St, Cleveland, Ohio 44113-1234              full, state -> OH, ZIP+4
Cleveland, OH 44113                                   partial (no street)
44113                                                 partial (ZIP only)
1234 Main St                                          refuse (plain typing)
PO Box 417, Cleveland, OH 44113                       full, street = "PO Box 417"
10 Downing St, London SW1A 2AA, United Kingdom        refuse (non-US)
```

## Build sequence

1. `frontend/shared/address-paste.js` — parser + `attach()` + undo UI + the
   small stylesheet (or fold the styles into the module; it is a status line and
   a highlight, not a component).
2. Wire **surface 1** (`addressBlock`) and review it live — it exercises the
   select, the disabled-shipping case and the mirror in one screen, so it is the
   real proving ground.
3. Wire **2 and 3** (mentor screens, textarea street).
4. Wire **4** (directory, layout-driven sub-fields).
5. Wire **5 and 6** (public forms; volunteer, then ZIP-rescue).
6. Guard test + the harness case table.

No feature flag is proposed: the module is inert unless a page loads it and calls
`attach`, and per-surface wiring is itself the rollout control. Say if you'd
rather gate it — that would mean a boot-read flag, which cannot be toggled from
`/setup` (`BOOT_READ_KEYS`), so it would be an overlay change per environment.

## Out of scope

- Address **validation** or deliverability (USPS, Smarty).
- Google Places type-ahead — ruled out for now; the module's `parse()` seam is
  where it would go if the heuristic proves too rough in practice.
- Parsing **name / email / phone** from a pasted contact block. Worth noting for
  later: `sessions/service.py:_contact_card` already *generates* exactly such a
  block for the Contact peek, so the two would round-trip if this is ever
  revisited.
- Widening the public intake forms to collect City and State.
- Any server-side parse. There is no Python twin, unlike `phone.format_us` —
  nothing in the API path needs to parse an address.
