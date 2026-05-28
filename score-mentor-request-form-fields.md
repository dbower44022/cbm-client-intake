# SCORE Mentor Request Form — Field Inventory

**Source:** https://score.tfaforms.net/111 (FormAssembly form 111)
**Captured:** 2026-05-28 from raw form HTML
**Query params present:** `address=44121`, `companyid=0030`, `origination=https://www.score.org/`

---

## Visible / applicant-facing fields

| # | Field label | Field id | Data type | Options |
|---|-------------|----------|-----------|---------|
| 1 | First Name | `tfa_3` | Text | — |
| 2 | Last Name | `tfa_7` | Text | — |
| 3 | Email Address | `tfa_1873` | Text (email) | — |
| 4 | Confirm Email Address | `tfa_2415` | Text (email) | — |
| 5 | Phone Number | `tfa_1874` | Text — placeholder `###-###-####` | — |
| 6 | Zip Code | `tfa_2243` | Text — placeholder `#####` | — |
| 7 | How would you like to receive notifications about this request? | `tfa_9` | Dropdown (select) | Email · Text Message |
| 8 | How would you like to meet with your mentor? | `tfa_2631` | Dropdown (select) | No Preference · Video · Phone · Email · In Person |
| 9 | Select an area you would like to be mentored in | `tfa_2682` | Dropdown (select) | *(see Area of Mentoring list below — 40 options)* |
| 10 | Please describe the business questions you need answered | `tfa_2667` | Textarea | — |
| 11 | Would you like to schedule an appointment now? | `tfa_2827` | Radio | Yes · No |
| 12 | Is your business already established? | `tfa_2646` | Radio | Yes · No *(Yes reveals fields 13–17)* |
| 13 | Business Name | `tfa_2703` | Text | — |
| 14 | Business Website | `tfa_2862` | Text | — |
| 15 | What type of business do you have? | `tfa_2649` | Dropdown (select) | *(see Business Type list below — 43 options)* |
| 16 | Year Formed | `tfa_2863` | Text — placeholder `####`, maxlength 4 | — |
| 17 | Number of Employees | `tfa_2864` | Text — placeholder `########`, maxlength 8 | — |
| 18 | Referrer Name | `tfa_2531` | Text | — |
| 19 | Workshop / Event | `tfa_2532` | Text | — |
| 20 | How did you hear about SCORE? | `tfa_2249` | Dropdown (select) | Online search · TV · Newspaper · Radio · Social media · SBA · Friend or relative · SCORE client or volunteer · Workshop/event · Other |
| 21 | Do you consent to receive marketing communication from SCORE? | `tfa_2854` | Dropdown (select) | Yes · No |
| 22 | Terms & Conditions consent | `tfa_2837` | Checkbox (single) | "By checking this box, you consent to receive communications from SCORE and acknowledge that you have read and agree to abide by SCORE'S Client Code of Conduct, Terms of Use, and Privacy Policy." |

> Note: every dropdown also carries a leading `Please select...` placeholder option (not a selectable value).

---

## Dropdown option lists (long)

### Field 9 — Select an area you would like to be mentored in (40 options)

Accounting & Finance · Advertising · Bookkeeping · Branding · Budgeting · Business Plan · Business Structure · Cash Flow · Communications Tech · Contracts · Customer Service · Cybersecurity · Digital Marketing · Disaster Prep & Recovery · Ecommerce · Financial Literacy · Franchising · Funding/Loans · Government Contracting · Government Regulations · Hardware & Equipment · Human Resources · Import & Export · Intellectual Property · Legal · Management & Operations · Marketing · Marketing Strategy · PR/Media · Pricing · Product Development · Sales · Social Media · Software & Applications · Strategy Development · Supply Chain Management · Tax Planning · Technology · Websites · Work/Life Balance

### Field 15 — What type of business do you have? (43 options)

Accounting & Tax Services · Advertising, Design, & Marketing · Agriculture · Animal & Veterinary Services · Architecture, Engineering, & Related Services · Arts, Entertainment & Recreation · Auto Repair & Mechanic · Beauty, Cosmetics & Salon Services · Business Consulting & Coaching · Childcare · Commercial & Residential Services · Construction · Counseling & Therapy · Distribution & Transportation of Goods · Education · Farming & Livestock · Fine Arts, Artisan, & Craft Work · Fishing & Hunting · Food & Beverage · Forestry · Funeral & Death Care Services · Information Technology · Manufacturing · Media & Publishing · Mining, Quarry, & Utilities · Nonprofit · Personal Care Services · Photography & Video Services · Professional Services · Public Relations & Communications · Real Estate · Recruiting & Staffing · Rental & Leasing · Restaurant & Bar · Retail · Social Assistance & Family Services · Transportation · Travel, Hospitality, & Tourism · Warehousing · Waste Management & Disposal · Website Development · Wellness, Healthcare, & Home Health · Wholesale

---

## Hidden / system / administrative fields (not shown to the applicant)

These are present in the form markup but are pre-filled, read-only, conditional-logic helpers, or FormAssembly bookkeeping — not data the applicant enters directly.

| Field label / purpose | Field id | Type |
|------------------------|----------|------|
| Chapter Name (pre-filled, readonly) | `tfa_2536` | Text — value `Cleveland` |
| Mentor Name (pre-filled, readonly) | `tfa_2537` | Text — value `Mentor Name` |
| AccountQueueIDSet? | `tfa_2852` | Checkbox |
| Allow clients to self-schedule (Chapter) | `tfa_2822` | Checkbox |
| Allow clients to self-schedule (Mentor) | `tfa_2824` | Checkbox |
| Scheduling Tool Full URL (Mentor) | `tfa_2825` | Text |
| Scheduling Tool Full URL (Chapter) | `tfa_2826` | Text |
| Request Limit Reached | `tfa_2759` | Dropdown — Yes / No |
| Which ID Provided | `tfa_2742` | Dropdown — Mentor / Location |
| Misc hidden inputs | `tfa_2745`, `tfa_2749`, `tfa_2747`, `tfa_2751`, `tfa_2705`, `tfa_2707`, `tfa_2699`, `tfa_2701`, `tfa_2758` | Hidden |
| FormAssembly bookkeeping | `tfa_dbCounters`, `tfa_dbFormId`, `tfa_dbResponseId`, `tfa_dbControl`, `tfa_dbWorkflowSessionUuid`, `tfa_dbTimeStarted`, `tfa_dbVersionId`, `tfa_switchedoff` | Hidden |

---

## Conditional logic notes

- **Field 12 (Is your business already established?)** — selecting **Yes** reveals fields 13–17 (Business Name, Business Website, What type of business, Year Formed, Number of Employees) via `data-conditionals`.
