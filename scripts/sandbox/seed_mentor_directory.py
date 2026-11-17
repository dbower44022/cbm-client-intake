"""Give the training system's public mentor directory twelve finished profiles.

The chapter demo website reads its Find a Mentor page from the training CRM.
The other seeders give a mentor a name, a status and little else, and leave
``publicProfile`` unticked, so the directory showed four cards, two of them
nearly empty (Doug, 11-17-26, option B). This fills twelve mentor profiles the
training seed already makes, with the fields the website draws
(``website/content.mentor_record``), and ticks ``publicProfile``:

* title, card summary (``mentorSummary``), About text, areas of expertise,
  industry experience, languages, accepting-new-clients, years of experience
  and sector on the mentor profile;
* a LinkedIn address on the mentor's Contact;
* a photograph from ``mentor-photos/``. Every face is machine-generated: no
  real person is shown as an invented mentor (Doug, 11-17-26, option A).

Joe Mentor and Matt Mentor are the training sign-ins. Only their website text
and photograph are replaced; their names and everything the training guide
relies on stay. The mentors with joke names stay off the website.

Unlike the other seeders this one CONVERGES: the values below are the showcase,
so a field holding anything else is overwritten. It touches only the twelve
named profiles, their Contacts and the fields listed. Every field and option is
checked against the live CRM first; an absent field or an unknown option is
reported and dropped, never sent. A photograph is uploaded only when the
profile's current one does not carry this file's name.

Read-only unless ``--apply``. Refuses any CRM but the two training systems
(``targets.py``). ``--preview FILE`` writes a stand-alone page of the cards and
profiles, drawn by the website's own code, and contacts no CRM at all.

    uv run python scripts/sandbox/seed_mentor_directory.py --preview /tmp/x.html
    uv run python scripts/sandbox/seed_mentor_directory.py --env-file ~/.config/cbm-bma/bma.env
    uv run python scripts/sandbox/seed_mentor_directory.py --env-file ~/.config/cbm-bma/bma.env --apply
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import os
import sys
from pathlib import Path
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import targets  # noqa: E402

PHOTOS = Path(__file__).resolve().parent / "mentor-photos"
#: Bump when a photograph file changes, so the next run uploads it again.
PHOTO_VERSION = "v1"
ENTITY = "CMentorProfile"


def _about(*paragraphs: str) -> str:
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)


#: The showcase. ``name`` is the stored profile name the seed gave it.
MENTORS: tuple[dict[str, Any], ...] = (
    {
        "name": "Joe Mentor",
        "mentorTitle": "Retired Operations Director, regional food manufacturer",
        "mentorSummary": "Thirty years running plants and warehouses. I help small "
                         "manufacturers and food businesses get control of cash, "
                         "inventory and the daily schedule.",
        "aboutMentor": _about(
            "I spent thirty years in operations, the last twelve as operations "
            "director for a regional food manufacturer with three plants and about "
            "400 people. I started on the line, so I know what a plan looks like from "
            "the floor.",
            "Most owners I meet are working too hard because the business has no "
            "rhythm: no weekly numbers, no standard way of doing the jobs that repeat, "
            "and too much cash sitting on the shelf as inventory. We fix those one at "
            "a time, starting with whatever is costing you the most sleep.",
            "I am straight-talking and numbers-first. Expect homework, and expect me "
            "to ask how it went."),
        "areaOfExpertise": ["Operations & Process Improvement", "Finance & Cash Flow Management",
                            "Business Strategy & Planning"],
        "industryExperience": ["Manufacturing & Industrial", "Hospitality, Restaurants & Food Service",
                               "Transportation and Logistics"],
        "fluentLanguages": ["English", "Spanish"],
        "acceptingNewClients": True,
        "yearsOfExperience": 30,
        "industrySector": "Manufacturing",
        "linkedin": "joe-mentor",
    },
    {
        "name": "Matt Mentor",
        "mentorTitle": "E-commerce consultant and former retail marketing director",
        "mentorSummary": "Fourteen years building online stores and marketing plans for "
                         "independent retailers. I help owners sell more online without "
                         "wasting money on ads.",
        "aboutMentor": _about(
            "I ran marketing for a chain of twenty specialty stores, then spent eight "
            "years consulting for independent retailers moving online. I have built "
            "stores on most of the common platforms and run paid advertising for "
            "businesses spending fifty dollars a month and fifty thousand.",
            "The questions I hear most are where to start online, whether advertising "
            "is worth it, and why the website gets visitors but no sales. I help you "
            "answer them with your own numbers rather than someone's sales pitch.",
            "Outside work I coach youth soccer and roast my own coffee, with mixed "
            "results."),
        "areaOfExpertise": ["E-Commerce", "Digital Marketing & Social Media", "Marketing & Branding",
                            "Retail and Merchandising"],
        "industryExperience": ["Retail & Consumer Products", "E-Commerce & Online Business",
                               "Advertising, Design, Marketing"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 14,
        "industrySector": "Retail Trade",
        "linkedin": "matt-mentor",
    },
    {
        "name": "Marta Delgado",
        "mentorTitle": "Restaurant owner and hospitality consultant",
        "mentorSummary": "Owned and ran two neighbourhood restaurants for eighteen years. "
                         "I help food businesses price their menus, control costs and keep "
                         "good staff.",
        "aboutMentor": _about(
            "I opened my first restaurant with a borrowed stove and a family recipe "
            "book, and ran two for eighteen years before selling them to my managers. "
            "I have also helped open food trucks, a bakery and a catering kitchen.",
            "Food businesses live and die on small numbers: food cost, labour cost, "
            "table turns. I help owners see those numbers every week and act on them, "
            "and I help with the people side too, because a good team is the hardest "
            "thing in this business to build.",
            "Hablo español. Many of my clients are first-generation owners, and I am "
            "happy to meet in whichever language is easiest for you."),
        "areaOfExpertise": ["Hospitality, Restaurants, Food Trucks, Lodging",
                            "Human Resources & Talent Management", "Finance & Cash Flow Management"],
        "industryExperience": ["Hospitality, Restaurants & Food Service", "Retail & Consumer Products"],
        "fluentLanguages": ["English", "Spanish"],
        "acceptingNewClients": True,
        "yearsOfExperience": 25,
        "industrySector": "Accommodation and Food Services",
        "linkedin": "marta-delgado",
    },
    {
        "name": "Ray Okonkwo",
        "mentorTitle": "Former bank lender and small-business finance advisor",
        "mentorSummary": "Twenty years as a commercial lender. I help owners get ready to "
                         "borrow, find the right kind of funding and read their own "
                         "financial statements.",
        "aboutMentor": _about(
            "I spent twenty years on the other side of the desk as a commercial "
            "lender, most of it with small-business and community development loans. "
            "I have read thousands of loan applications and know why most of them are "
            "turned down.",
            "I help owners get ready before they ask: clean financial statements, a "
            "realistic forecast and a clear story of what the money is for. We also "
            "look at alternatives to a bank loan, from microlenders and grants to "
            "equipment finance.",
            "If you have never felt comfortable with a balance sheet, that is exactly "
            "where we start."),
        "areaOfExpertise": ["Funding & Capital Access", "Finance & Cash Flow Management", "Accounting"],
        "industryExperience": ["Financial Services & Banking", "Professional Services",
                               "Construction & Real Estate"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 20,
        "industrySector": "Finance and Insurance",
        "linkedin": "ray-okonkwo",
    },
    {
        "name": "Priya Raman",
        "mentorTitle": "Software founder and technology advisor",
        "mentorSummary": "Built and sold a software company. I help owners choose the "
                         "right technology, use AI sensibly and get a website that "
                         "actually brings in customers.",
        "aboutMentor": _about(
            "I founded a scheduling-software company, grew it to forty people and "
            "sold it after eleven years. Before that I was a software engineer for a "
            "large insurer.",
            "Small businesses are sold a great deal of technology they do not need. I "
            "help you work out which tools will save you time, how to keep customer "
            "data safe, and where artificial intelligence can genuinely help a small "
            "team today.",
            "I also mentor technology start-ups on product, pricing and the first "
            "sales hire."),
        "areaOfExpertise": ["Technology & Digital Transformation",
                            "Artificial Intelligence for Small Businesses", "Websites",
                            "Startup Launch & Entrepreneurship"],
        "industryExperience": ["Technology & Software", "Cybersecurity", "Professional Services"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 19,
        "industrySector": "Information",
        "linkedin": "priya-raman",
    },
    {
        "name": "Gordon Whitfield",
        "mentorTitle": "Retired CEO, industrial distribution",
        "mentorSummary": "Led a family-owned distribution company for twenty-five years "
                         "and sold it. I help owners plan for growth, succession and "
                         "an eventual sale.",
        "aboutMentor": _about(
            "I joined my family's industrial supply company when it had eleven "
            "employees and led it for twenty-five years, through two recessions and "
            "three acquisitions, before selling it to a national distributor.",
            "Most of my mentoring is with established owners asking what comes next: "
            "how to grow past the point where they can do everything themselves, who "
            "takes over, and what the business is really worth.",
            "I am not taking new clients at the moment, but I am glad to join a "
            "conversation another mentor has started."),
        "areaOfExpertise": ["Mergers, Acquisitions & Exit Planning", "Leadership & Executive Coaching",
                            "Strategic Planning"],
        "industryExperience": ["Manufacturing & Industrial", "Transportation and Logistics"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": False,
        "yearsOfExperience": 38,
        "industrySector": "Wholesale Trade",
        "linkedin": "gordon-whitfield",
    },
    {
        "name": "Nina Barsotti",
        "mentorTitle": "Brand strategist and former agency creative director",
        "mentorSummary": "Twenty years in advertising agencies. I help small businesses "
                         "find a clear message, a look that fits and marketing they can "
                         "keep up.",
        "aboutMentor": _about(
            "I was creative director at a mid-sized advertising agency, working with "
            "brands large and small, before going independent to work with local "
            "businesses.",
            "Good marketing starts with a clear answer to one question: why should a "
            "customer choose you? We find that answer together, then turn it into a "
            "name, a look, a website and a plan you can keep up with a small budget.",
            "I especially enjoy working with salons, studios, boutiques and other "
            "businesses where the owner is the brand."),
        "areaOfExpertise": ["Marketing & Branding", "Digital Marketing & Social Media",
                            "Customer Experience & Service Excellence"],
        "industryExperience": ["Advertising, Design, Marketing", "Media, Marketing & Publishing",
                               "Beauty, Cosmetics and Salon Services"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 21,
        "industrySector": "Professional, Scientific, and Technical Services",
        "linkedin": "nina-barsotti",
    },
    {
        "name": "Curtis Boyle",
        "mentorTitle": "General contractor and construction business coach",
        "mentorSummary": "Ran a residential and light-commercial contracting firm for "
                         "twenty-two years. I help trades businesses bid, schedule and "
                         "get paid.",
        "aboutMentor": _about(
            "I started as a carpenter, became a general contractor and ran a "
            "residential and light-commercial firm with forty people in the field.",
            "Contractors rarely fail for lack of work. They fail on bids that miss "
            "costs, jobs that run late and invoices that are paid ninety days after "
            "the work. I help with estimating, job costing, scheduling crews and "
            "managing cash between draws.",
            "I also help tradespeople going out on their own for the first time with "
            "licensing, insurance and finding their first customers."),
        "areaOfExpertise": ["Operations & Process Improvement", "Sales & Business Development",
                            "Government Contracting and Regulations"],
        "industryExperience": ["Construction & Real Estate", "Commercial and Residential Services",
                               "Architecture, Engineering"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 26,
        "industrySector": "Construction",
        "linkedin": "curtis-boyle",
    },
    {
        "name": "Helena Vance",
        "mentorTitle": "Nonprofit executive director and fundraising advisor",
        "mentorSummary": "Led two community nonprofits over twenty years. I help new "
                         "nonprofits build a board, raise money and run programs that "
                         "funders trust.",
        "aboutMentor": _about(
            "I was executive director of a youth-services nonprofit and later of a "
            "community health organization, growing each from a handful of staff to "
            "budgets of several million dollars.",
            "I help founders through the early years: forming a working board, "
            "writing the first grant applications, designing programs whose results "
            "can be measured, and moving from one large funder to many.",
            "I am not taking new clients at the moment. Please request a mentor and "
            "we will match you with someone who can help."),
        "areaOfExpertise": ["Nonprofit Management & Fundraising", "Program Design & Implementation",
                            "Social Assistance & Family Services"],
        "industryExperience": ["Nonprofit & Social Impact", "Healthcare & Medical", "Education"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": False,
        "yearsOfExperience": 24,
        "industrySector": "Health Care and Social Assistance",
        "linkedin": "helena-vance",
    },
    {
        "name": "Dmitri Sokolov",
        "mentorTitle": "Former international trade manager, manufacturing",
        "mentorSummary": "Managed exports and overseas suppliers for an equipment "
                         "manufacturer. I help businesses sell abroad and source "
                         "products safely.",
        "aboutMentor": _about(
            "For eighteen years I managed export sales and overseas suppliers for an "
            "industrial equipment manufacturer, opening markets in Canada, Mexico and "
            "Eastern Europe.",
            "Selling or buying across borders is less mysterious than it looks, but "
            "the mistakes are expensive. I help with choosing a first export market, "
            "pricing for it, shipping terms, finding reliable suppliers and the "
            "paperwork in between.",
            "I am not taking new clients at the moment."),
        "areaOfExpertise": ["International Business & Market Expansion", "Transportation and Logistics",
                            "Product Development & Innovation"],
        "industryExperience": ["Manufacturing & Industrial", "Transportation and Logistics",
                               "Energy & Utilities"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": False,
        "yearsOfExperience": 27,
        "industrySector": "Manufacturing",
        "linkedin": "dmitri-sokolov",
    },
    {
        "name": "Angela Fournier",
        "mentorTitle": "CPA and small-business accounting advisor",
        "mentorSummary": "A certified public accountant who has kept the books for "
                         "hundreds of small businesses. I help owners understand their "
                         "numbers and plan for taxes.",
        "aboutMentor": _about(
            "I am a certified public accountant and ran my own accounting practice "
            "for fifteen years, serving shops, salons, contractors and nonprofits.",
            "I help entrepreneurs set up bookkeeping that works from the first day, "
            "read their profit and loss statement, plan for taxes rather than being "
            "surprised by them, and decide when it is time to hire their first "
            "employee.",
            "Hablo español, and I am happy to work in either language."),
        "areaOfExpertise": ["Accounting", "Finance & Cash Flow Management",
                            "Human Resources & Talent Management"],
        "industryExperience": ["Accounting and Bookkeeping", "Business Consulting and Coaching",
                               "Professional Services"],
        "fluentLanguages": ["English", "Spanish"],
        "acceptingNewClients": True,
        "yearsOfExperience": 23,
        "industrySector": "Professional, Scientific, and Technical Services",
        "linkedin": "angela-fournier",
    },
    {
        "name": "Beatrice Nolan",
        "mentorTitle": "Retired HR executive and leadership coach",
        "mentorSummary": "Thirty years in human resources, ending as head of people for "
                         "a regional health system. I help owners hire well, lead well "
                         "and keep their best people.",
        "aboutMentor": _about(
            "I spent thirty years in human resources, finishing as vice president of "
            "people for a regional health system with six thousand employees.",
            "Small-business owners rarely have anyone to talk to about people "
            "problems. I help with hiring the first few employees, writing a simple "
            "handbook, paying fairly, handling a difficult conversation, and growing "
            "into the role of leader rather than doer.",
            "I also coach owners of childcare centres, group homes and wellness "
            "businesses, where staffing is the whole business."),
        "areaOfExpertise": ["Human Resources & Talent Management", "Leadership & Executive Coaching",
                            "Compliance & Accreditation Audits"],
        "industryExperience": ["Healthcare & Medical", "Childcare", "Wellness and Fitness"],
        "fluentLanguages": ["English"],
        "acceptingNewClients": True,
        "yearsOfExperience": 30,
        "industrySector": "Health Care and Social Assistance",
        "linkedin": "beatrice-nolan",
    },
)

#: Profile fields the showcase writes (everything but ``name`` and ``linkedin``).
PROFILE_FIELDS = ("mentorTitle", "mentorSummary", "aboutMentor", "areaOfExpertise",
                  "industryExperience", "fluentLanguages", "acceptingNewClients",
                  "yearsOfExperience", "industrySector", "publicProfile")
LINKEDIN_FIELD = "cLinkedInProfile"


def slug(name: str) -> str:
    from website.content import slugify
    return slugify(name)


def photo_name(name: str) -> str:
    return f"mentor-{slug(name)}-{PHOTO_VERSION}.jpg"


def photo_path(name: str) -> Path:
    return PHOTOS / f"{slug(name)}.jpg"


def linkedin_url(m: dict[str, Any]) -> str:
    return f"https://www.linkedin.com/in/{m['linkedin']}-sandbox"


def wanted(m: dict[str, Any]) -> dict[str, Any]:
    payload = {k: m[k] for k in PROFILE_FIELDS if k in m}
    payload["publicProfile"] = True
    return payload


# --------------------------------------------------------------- preview ---

def write_preview(out: str) -> None:
    """The cards and every profile, drawn by the website's own functions from
    the data above. No CRM is contacted."""
    from website import content

    css = (Path(ROOT) / "website" / "static" / "website.css").read_text()
    cards, profiles = [], []
    for m in MENTORS:
        first, _, last = m["name"].partition(" ")
        rec = {**wanted(m), "id": slug(m["name"]), "name": m["name"], "mentorStatus": "Active",
               "profilePhotoId": "x"}
        mr = content.mentor_record(rec, {"firstName": first, "lastName": last,
                                         LINKEDIN_FIELD: linkedin_url(m)}, True)
        data = base64.b64encode(photo_path(m["name"]).read_bytes()).decode()
        src = f"data:image/jpeg;base64,{data}"
        card = content.mentor_card("", mr).replace(content.esc(content.photo_src("", mr)), src)
        cards.append(card.replace(f'href="/mentors/{mr["slug"]}/"', f'href="#{mr["slug"]}"'))
        profiles.append(f'<section id="{mr["slug"]}" style="margin:48px 0;border-top:2px solid #ccc;'
                        f'padding-top:24px">{content.profile_html(mr, src)}</section>')
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Mentor Directory Preview</title><style>{css}"
        ":root{--bg:#eef0f2;--sheet:#fff}"
        "@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#1b1d20}}"
        ":root[data-theme=dark]{--bg:#1b1d20}"
        "body{margin:0;padding:16px;font-family:system-ui,sans-serif;background:var(--bg);color:#222}"
        ".sheet{background:var(--sheet);max-width:none;padding:24px;border-radius:8px}"
        "</style></head><body><div class='sheet'>"
        "<h1>Find a Mentor — preview</h1>"
        "<p>Drawn by the website's own code from the drafted data. Nothing has been "
        "written to any CRM. Every face is machine-generated. The live page shuffles "
        "the cards on each visit.</p>"
        f"<div class='cmw-root cmw-directory'><ul class='cmw-grid'>{''.join(cards)}</ul></div>"
        f"{''.join(profiles)}</div></body></html>"
    )
    Path(out).write_text(page)
    print(f"Preview written: {out}")


# ------------------------------------------------------------------ apply ---

def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return sorted(a or []) == sorted(b or [])
    if isinstance(a, str) or isinstance(b, str):
        return " ".join(str(a or "").split()) == " ".join(str(b or "").split())
    return a == b


async def run(env_file: str | None, apply: bool) -> int:
    from core.espo import EspoClient, EspoError

    base, api_key, timeout = targets.api_connection(env_file)
    target = targets.resolve(base)
    if target is None:
        print(targets.refusal(base))
        return 2
    print(f"Training system: {target.label} ({base}) — {'APPLY' if apply else 'dry run'}")
    client = EspoClient(base, api_key, timeout)

    fields = await client.metadata(f"entityDefs.{ENTITY}.fields") or {}
    contact_fields = await client.metadata("entityDefs.Contact.fields") or {}
    has_linkedin = LINKEDIN_FIELD in contact_fields

    def checked(payload: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for key, value in payload.items():
            spec = fields.get(key)
            if not spec:
                print(f"  ! {ENTITY}.{key} is not on this CRM — dropped")
                continue
            options = spec.get("options")
            if options and isinstance(value, list):
                bad = [v for v in value if v not in options]
                if bad:
                    print(f"  ! {key}: not an option here, dropped: {bad}")
                value = [v for v in value if v in options]
            elif options and isinstance(value, str) and value not in options:
                print(f"  ! {key}: {value!r} is not an option here — dropped")
                continue
            out[key] = value
        return out

    select = ",".join(("id", "name", "mentorStatus", "contactRecordId", "profilePhotoId",
                       "profilePhotoName") + PROFILE_FIELDS)
    rows = (await client.list(ENTITY, select=select, max_size=200)).get("list", []) or []
    by_name: dict[str, list[dict]] = {}
    for r in rows:
        by_name.setdefault(r.get("name") or "", []).append(r)

    problems = 0
    for m in MENTORS:
        found = by_name.get(m["name"], [])
        if len(found) != 1:
            print(f"- {m['name']}: {len(found)} profiles with that name — skipped")
            problems += 1
            continue
        rec = found[0]
        if rec.get("mentorStatus") != "Active":
            print(f"  ! {m['name']} is {rec.get('mentorStatus')}, not Active — the website will not show them")
        payload = checked(wanted(m))
        change = {k: v for k, v in payload.items() if not _same(rec.get(k), v)}
        photo = photo_name(m["name"])
        new_photo = rec.get("profilePhotoName") != photo
        print(f"- {m['name']}: {len(change)} field(s) to set"
              f"{' (' + ', '.join(change) + ')' if change else ''}"
              f"{'; photo to upload' if new_photo else ''}")
        try:
            if apply and new_photo:
                data = base64.b64encode(photo_path(m["name"]).read_bytes()).decode()
                change["profilePhotoId"] = await client.upload_attachment(
                    filename=photo, content_type="image/jpeg", data_base64=data,
                    related_type=ENTITY, field="profilePhoto")
            if apply and change:
                await client.update(ENTITY, rec["id"], change)
            contact_id = rec.get("contactRecordId")
            if has_linkedin and contact_id:
                contact = await client.get("Contact", contact_id, select=f"id,{LINKEDIN_FIELD}")
                if contact.get(LINKEDIN_FIELD) != linkedin_url(m):
                    print(f"  contact: LinkedIn to set")
                    if apply:
                        await client.update("Contact", contact_id, {LINKEDIN_FIELD: linkedin_url(m)})
            elif not contact_id:
                print("  ! no linked Contact — LinkedIn not set, and the website falls back to the profile name")
        except EspoError as exc:
            print(f"  ! refused: {exc}")
            problems += 1
    if not apply:
        print("Dry run: nothing written. Add --apply to write.")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--preview", metavar="FILE", help="write a preview page and stop")
    targets.add_env_file_argument(parser)
    args = parser.parse_args()
    if args.preview:
        write_preview(args.preview)
        return 0
    return asyncio.run(run(args.env_file, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
