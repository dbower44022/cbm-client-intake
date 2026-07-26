# Analytics — User Guide

A plain-language guide to the **Analytics** app for Cleveland Business Mentors
staff. It covers viewing dashboards, building your own metrics, composing pages,
and the record-level analytics that appear on a mentor's record.

> **Where it lives:** the **Analytics** tile on the portal home (or go straight to
> `/analytics`). You must be signed in through the portal first.
>
> **Who can use it:** anyone on the **Analytics Admin Team** (or a CRM admin) can
> both *view* and *build* analytics. Viewing can be opened to more teams per
> deployment; building is always limited to the Analytics Admin Team. Individual
> panels can also be restricted to specific teams.

---

## 1. The big picture — three building blocks

Analytics is made of three reusable pieces:

| Piece | What it is |
|---|---|
| **Metric** | A reusable, named piece of data — e.g. "Total Active Mentors", "Engagements by status", "Contributions received per month". A metric produces one of four shapes: a **single number**, a **trend over time**, a **breakdown by category**, or a **list of records**. |
| **Panel** | A metric shown a particular way (a big number, a line chart, bars, a pie, or a table). |
| **Page** | An ordered collection of panels. A page is either a **system dashboard** (org-wide) or a **record tab** (shown on an individual record, e.g. a mentor). |

You build a metric once and reuse it on any number of panels and pages.

---

## 2. Viewing a dashboard

Open **Analytics**. You'll see the **System Analytics** dashboard (and any other
pages you've been given access to, shown as tabs across the top).

Each dashboard has:

- **A time-range selector** (top left) — Last 7 / 30 / 90 days, This quarter,
  Year to date, Last 12 months, All time. Time-aware panels (trends) update to the
  range you pick; panels that show a current total or breakdown ignore it.
- **A Refresh button** (top right) — recomputes every panel on the page right now.
- **Panels** — each shows a small freshness note: **"live"** (computed on the spot)
  or **"as of …"** (served from a recent cached calculation).

**What ships by default (the System Analytics page):**

- **Total Active Mentors** — a count.
- **Active Client Engagements** — a count.
- **New client engagements per month** — a trend line.
- **Engagements by status** — a bar breakdown.
- **Oldest unassigned engagements** — a table; click an engagement to open it in
  the CRM.

### The portal home dashboard

If a dashboard has been marked **"Show on portal home"**, its panels also appear on
the portal landing page (above your app tiles), so the key numbers greet you when
you sign in. Only people who can view that dashboard see it there; everyone else's
home page is unchanged. There's an **"Open Analytics →"** link to jump to the full
app.

---

## 3. Record analytics — the Mentor Analytics tab

Analytics can also be scoped to a **single record**. Today this appears as an
**Analytics** tab inside **Mentor Administration** (`/mentoradmin`): open a mentor,
click **Analytics**, and you see that mentor's own numbers (for example, their
engagement counts) — filtered automatically to just that mentor.

Two things to know:

- **It respects permissions.** The tab shows a mentor's analytics only if you can
  already open that mentor's record. The numbers are calculated as *you*, so you
  never see data your CRM access wouldn't already allow.
- **It only appears if someone has built a mentor-scoped page.** If no analytics
  have been set up for mentors yet, the tab shows a short "ask an analytics author"
  message. See §5 for how to build one.

*(More record types — companies, engagements, partners, funders — can be added the
same way in future; the mentor record is the first.)*

---

## 4. Who sees what

- **A whole page** can be limited to specific **teams** (the "Who can view" field
  when composing a page). Left blank, it uses the deployment's default analytics
  view team.
- **A single panel** can be limited to specific teams too ("Visible to" on the
  panel). Someone who lacks a panel's team simply doesn't see that panel — the rest
  of the page renders normally.
- **System dashboards** show org-wide totals, computed with a service account, so
  everyone entitled sees the same numbers.
- **Record tabs** are computed as the signed-in user, so they're naturally limited
  to what that person's CRM access allows.

---

## 5. Building your own analytics (the Manage view)

If you're on the Analytics Admin Team, you'll see a **Manage** button in the top
bar. It has two sections: **Metrics** and **Pages**.

### 5.1 Building a metric

Click **Metrics → + New metric**. Fill in:

1. **Name** — e.g. "Active partners". (The system makes a stable internal key from
   the name.)
2. **Record type** — which CRM records to measure (Client Engagements, Mentors,
   Companies, Contacts, Partners, Funders, Sessions, Contributions, Information
   Requests).
3. **Measure** — how to summarize them:
   - **Count of records** → a single number.
   - **Sum of a field** / **Average of a field** → a single number over a numeric
     field.
   - **Group by a field** → a breakdown (bars or pie).
   - **Over time (monthly)** → a trend line, bucketed by month.
   - **List of records** → a table.
4. **Filters** (optional) — narrow the records: pick a field, an operator, and a
   value. Operators: `=`, `≠`, `in` (comma-separated list), `>`, `<`, is empty,
   is not empty, and two **relative-date** operators — **"in the last…"** and
   **"older than…"**. Pick one of those on a date field (e.g. *Created At*) and
   the value becomes a number plus a **days / weeks / months** unit — so "Count
   of sessions created **in the last 30 days**" is: record type *Sessions*,
   measure *Count of records*, filter *Created At · in the last · 30 · days*. The
   window is relative to when the metric runs (a cached metric rolls it forward
   on each refresh), so you never have to edit dates.
5. **Show as** — the visualization (offered options match the measure you chose).
6. **Data freshness** — **Cached** (recalculated in the background about hourly —
   best for anything that scans a lot of records) or **Live** (recalculated every
   view — best for a quick count).
7. **Applies to** — where the metric can be used: **System (org-wide)** and/or one
   or more **record types**. If you tick a record type, a **Record link field**
   appears — enter the field that ties the data to that record (for example,
   `mentorProfileId` to count a mentor's engagements). Start typing to pick from the
   record's link fields.
8. **Preview** — click it to see the metric computed against real data before you
   save.

Click **Save metric**. It now appears in the metric library and can be placed on
pages.

**Editing / deleting:** use the **Edit** / **Delete** links in the metric list. A
metric that's used by a page can't be deleted until you remove it from that page
(the app tells you which page).

**Built-in metrics** ship with the app and are shown with a **built-in** tag. Most
carry a **Customize** link — clicking it makes an editable copy you can change like
any metric; a **Reset to default** link then appears to revert it. (A few built-ins
read the app's own operational data and can't be edited in the builder; those have
no Customize link, but you can still place them on pages.)

### 5.2 Composing a page

Click **Pages → + New page**. Fill in:

1. **Title** and optional **Subtitle**.
2. **Where it appears** — **System (org-wide dashboard)** or **Record tab: <type>**
   (e.g. Record tab: Mentors). This decides where the page shows up and which
   metrics you can add (a mentor page only offers mentor-scoped metrics).
3. **Default time range** — the range the page opens with.
4. **Who can view** — teams allowed to see the page (blank = the default view team).
5. **Show this dashboard on the portal home** — (system pages only) surfaces the
   page on everyone's portal landing page.
6. **Panels** — click **+ Add panel** for each: pick a **metric**, give the panel a
   **title**, choose **Show as**, set a **width** (3–12 columns out of 12), and
   optionally limit it to certain teams (**Visible to**). Reorder with the ↑ / ↓
   buttons.

Click **Save page**. System pages appear as tabs in the viewer; a record-tab page
shows up on that record type's Analytics tab.

### 5.3 Editing the main dashboard (and putting a metric on it)

The **System Analytics** dashboard (the one you see first) ships built-in, but you
can edit it — add, remove, or reorder its panels, including your own metrics:

1. Go to **Manage → Pages**. You'll see **System Analytics** with a **built-in**
   tag and an **Edit / customize** link.
2. Click **Edit / customize**. The page opens in the editor with all of its current
   panels already loaded (it makes an editable copy the first time).
3. To **add your metric to the main page**: click **+ Add panel**, pick your metric,
   set its title / chart type / width, and (optionally) which teams can see it.
4. To **remove** a built-in panel, click its **Remove**; to **reorder**, use ↑ / ↓.
5. Leave **"Show this dashboard on the portal home page"** ticked if you want it on
   everyone's landing page. Click **Save page**.

Your edits take over from the built-in version immediately. Changed your mind? The
page now shows a **Reset to default** link that restores the original built-in
dashboard. (Built-in **metrics** work the same way — **Customize** to edit,
**Reset to default** to revert.)

> **So the short answer to "how do I show a new metric on the main page":** build
> the metric (§5.1), then **Edit / customize** the System Analytics page and **+ Add
> panel** with it.

---

## 6. What data can metrics use?

- **The CRM** — accounts, contacts, mentors, engagements, partners, funders,
  sessions, contributions, information requests.
- **The app's own operational data** — e.g. **Submissions received per month** and
  the **submission queue by status** come from the intake pipeline's own database,
  not the CRM. (These need the app's database to be configured; if it isn't, those
  panels show a short "not configured" note.)
- **Currency rollups** — e.g. **Contributions received per month** sums dollar
  amounts and displays them as `$…`.

---

## 7. Good to know / current limits

- **Caching vs live.** Heavy metrics (anything that scans many records) should be
  **Cached** — they refresh in the background and load instantly. **Live** metrics
  recompute every view; use them for cheap counts. Record-tab metrics always run
  live (and only over that one record's data), so they're fast and always current.
- **A metric that can't be computed** (CRM hiccup, a data source that isn't
  configured) shows a short message in its panel — it never breaks the rest of the
  page.
- **Not yet available:** clicking a chart to "drill down" into the underlying rows,
  exporting to CSV/Excel, and personal (per-user) dashboards. Tables already link
  each row to its CRM record.

---

## 8. FAQ

**I don't see the Manage button.** You're not on the Analytics Admin Team (or the
app's database isn't configured, which authoring needs). Ask a CBM administrator.

**A panel says "not configured on this deployment."** That metric reads the app's
operational database, which isn't attached in this environment. It'll work where the
database is configured (production/test).

**The Mentor Analytics tab says no analytics are set up.** No one has built a
mentor-scoped page yet — see §5. Build a metric with **Applies to → Mentors** and a
record link field, then a page with **Where it appears → Record tab: Mentors**.

**Numbers look stale.** Cached panels show "as of …". Click **Refresh** to
recompute the page now.

**Who can see the dashboard on the portal home?** Only people allowed to view that
dashboard. It's marked "Show on portal home" by whoever built the page.

---

*Related: the deployment/activation runbook is `ANALYTICS-SETUP.md`. The design and
build record is `prds/analytics-app-plan.md`.*
