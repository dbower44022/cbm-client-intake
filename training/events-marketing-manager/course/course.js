/*
 * The course content — the whole course, as data.
 *
 * This file is the point of the architecture. The Artifact page (index.html)
 * is a thin player over it, and when the course graduates into the application
 * that page renders this same file. Moving the course re-renders the data and
 * rewrites no content.
 *
 * Two rules for anything written in here:
 *
 * 1. NEVER type the organisation's name. Write {{org}} and {{abbr}}; the
 *    player substitutes them from the page's own meta tags, which is the
 *    application's mechanism too (core/branding.py rewrites the served page).
 *    tests/test_shared_branding.py fails on a hardcoded name the moment this
 *    becomes a served page.
 * 2. Use the words on the screen — "Show this event", not publishToWebsite.
 *
 * A video with `url: null` is not recorded yet. The player says so and names
 * the recording script that produces it; it never pretends the video exists.
 */

window.COURSE = {
  title: "Running an event",
  audience: "The events marketing manager",
  blurb: "Create an event, market it, run its delivery, follow it up, and read what it did. " +
         "Two applications, one job.",
  signIn: "Mark Marketing — the Marketing Admin Team holds Event Administration " +
          "and Marketing Management alike, so the whole arc is one sign-in.",

  modules: [
    {
      id: "m1",
      title: "Create the event",
      state: "ready",
      summary: "The screen that gives an event its web address, and the four fields that " +
               "carry behaviour.",
      slides: [
        {
          title: "Create it here, not in the CRM",
          shot: {
            file: "m1-event-list.png",
            caption: "The event list. The Shown column on the right reads back what the " +
                     "three visibility controls add up to.",
            alt: "The Event Administration list, with a + New event button above it and a " +
                 "Shown column on the right of each row."
          },
          body: [
            "This screen is what gives an event its web address. An event typed straight " +
            "into the CRM has no page, so nothing can link to it and nobody can register.",
            "The public workshops and webinars page is built and live, but the marketing " +
            "site has not " +
            "been redirected to it yet. Until that one redirect is added, this tool and " +
            "the live site are separate worlds."
          ],
          note: "Everything in this module is live on the training sandbox today."
        },
        {
          title: "The fields that carry behaviour",
          shot: {
            file: "m1-form-behaviour-fields.png",
            caption: "Title, Format, Capacity and Registration closes on the new-event form.",
            alt: "The top of the event form showing the Title, Format, Capacity and " +
                 "Registration closes fields."
          },
          body: [
            "Most of the form is description and category. Four fields change what the " +
            "application does."
          ],
          facts: [
            ["Title", "Required, and it generates the web address — which is then fixed. " +
                      "Later title edits do not move the address, so links you have already " +
                      "shared keep working."],
            ["Format", "This is what decides whether a Zoom webinar gets created. Virtual " +
                       "and Hybrid get one; In-Person does not."],
            ["Capacity", "A seat cap. Empty or 0 means unlimited. Zero does not mean full."],
            ["Registration closes", "Leave it empty and registration closes when the event starts."]
          ]
        },
        {
          title: "Three separate questions decide who sees it",
          shot: {
            file: "m1-publishing-group.png",
            caption: "The Publishing group: Show this event, Audience and Display from, " +
                     "the three controls in one place.",
            alt: "The Publishing group of the event form, showing the Show this event tick, " +
                 "the Audience choice and the Display from control."
          },
          body: [
            "They are read in this order, and each one can hide the event on its own."
          ],
          facts: [
            ["Show this event", "Decides whether. Off by default. Unticked, the event is on " +
                                "no page at all — not the website, not the portal. Unticking " +
                                "hides it at once."],
            ["Audience", "Decides where. Public is the website and the portal calendar. " +
                         "Internal is the portal calendar only."],
            ["Display from", "Decides when. Before that moment the event is on no page and " +
                             "nobody can register. Use it to prepare an event now and " +
                             "announce it later."]
          ],
          note: "The Shown column in the event list reads the result back: Hidden, Appears " +
                "with a date, Public, Internal, or Internal and limited."
        },
        {
          title: "Zoom, and the two things it is not",
          shot: {
            file: "m1-zoom-button.png",
            caption: "Create / sync Zoom webinar, on a saved Virtual event.",
            alt: "The event screen with the Create / sync Zoom webinar button."
          },
          body: [
            "Create / sync Zoom webinar provisions the webinar under the shared Zoom host " +
            "and stores its ID and join link on the event. Registration is auto-approved, " +
            "so people who sign up on the website are added to the webinar."
          ],
          facts: [
            ["Virtual or Hybrid, and Public", "An Internal event never gets a Zoom webinar, " +
             "even from the button. An Internal event takes a Join URL you paste instead — " +
             "your own Zoom room, Meet, Teams."],
            ["It syncs the four fields Zoom cares about", "Editing the title, time, duration " +
             "or summary updates the webinar too. Changing capacity, topic or publishing " +
             "deliberately leaves it alone, so Zoom does not email every registrant that " +
             "the host updated the event."],
            ["Cancelling cancels it", "Setting Status to Cancelled cancels the webinar and " +
             "tells registrants. Switching a Virtual event to In-Person cancels it too, so " +
             "nobody holds a link to a room nobody will host."]
          ]
        },
        {
          title: "Limit to teams is not privacy",
          shot: {
            file: "m1-limit-to-teams.png",
            caption: "Limit to teams, which only appears once Audience is Internal.",
            alt: "The event form with Audience set to Internal and the Limit to teams box " +
                 "below it."
          },
          body: [
            "On an Internal event, Limit to teams decides who sees it on the portal. It is " +
            "not a permission: anyone who can read events in the CRM can still find it.",
            "Keep genuinely confidential meetings off the calendar altogether."
          ]
        },
        {
          title: "Give it a graphic, or it has no picture",
          shot: {
            file: "m1-event-graphic.png",
            caption: "The Event graphic control in the Content group: Choose image…, then " +
                     "Upload graphic.",
            alt: "The Content group of the event form showing the Event graphic control with " +
                 "its Choose image and Upload graphic buttons."
          },
          body: [
            "Without a graphic the website's calendar card falls back to the recording's " +
            "video thumbnail — and an upcoming event has no recording, so it would have no " +
            "picture at all.",
            "Save the event first. The graphic attaches to a saved event, so the control " +
            "asks you to save before it can accept an upload."
          ],
          facts: [
            ["What it takes", "JPEG, PNG, WebP or GIF, up to 5 MB."],
            ["It always wins", "An uploaded graphic beats the video thumbnail, including on " +
             "past events — so you can replace an unflattering auto-generated frame."],
            ["It is only public while the event is shown", "Untick Show this event and the " +
             "picture becomes as unreachable as the page."]
          ]
        },
        {
          title: "Presenters are copied once, then the event's own",
          shot: {
            file: "m1-presenters.png",
            caption: "The Presenters group with two entries — a mentor and a guest — and " +
                     "the Edit, photo, Up, Down and Remove controls on each row.",
            alt: "The Presenters group of the event form with two presenter entries listed."
          },
          body: [
            "Adding a mentor copies their public biography, their mentor title and their " +
            "photo onto this event's presenter entry. Adding anyone else brings their title " +
            "and company from their contact record.",
            "From then on the entry is the event's own text. Editing it touches nothing on " +
            "the person's record, and it is never re-copied — a mentor who rewrites their " +
            "profile next month changes nothing on this page. That is deliberate: a past " +
            "event's page is the record of what was presented."
          ],
          note: "Show presenter biographies is one tick on the event. To hide one " +
                "presenter's biography while showing the others, leave theirs empty."
        }
      ],
      videos: [
        {
          title: "Create a virtual public webinar",
          shows: "The form end to end, the four behaviour fields, the save, then " +
                 "Create / sync Zoom webinar and the Shown column reading it back.",
          url: null,
          script: "recording-scripts/module-1-create.md",
          section: "V1"
        },
        {
          title: "Create an internal event limited to teams",
          shows: "Audience Internal, Limit to teams, the Join URL box appearing in place of " +
                 "the Zoom button, Takes registrations, and the result on the portal.",
          url: null,
          script: "recording-scripts/module-1-create.md",
          section: "V2"
        },
        {
          title: "The graphic and the presenters",
          shows: "Choose image and Upload graphic, then adding a mentor presenter and a " +
                 "guest, editing an entry, ordering them, and Show presenter biographies.",
          url: null,
          script: "recording-scripts/module-1-create.md",
          section: "V3"
        }
      ]
    },

    {
      id: "m2",
      title: "Market the event",
      state: "held",
      heldBecause: "Promote this event and the event's Campaigns tab are switched off " +
                   "(EVENT_PROMOTE), and their live pass is still owed. A video cannot be " +
                   "recorded against a screen that is off, and a screen that has not had " +
                   "its live pass may still change.",
      summary: "One click makes a Draft campaign per channel, linked to the event. " +
               "Building and sending stay yours.",
      slides: [],
      videos: []
    },

    {
      id: "m3",
      title: "Run the delivery",
      state: "planned",
      summary: "Registrations, capacity and the waitlist, cancelling, check-in, and the " +
               "eight email templates.",
      slides: [],
      videos: []
    },

    {
      id: "m4",
      title: "Follow up",
      state: "planned",
      summary: "The five follow-ups, who gets which, and publishing the recording.",
      slides: [],
      videos: []
    },

    {
      id: "m5",
      title: "See what it did",
      state: "planned",
      summary: "Attendance, the event and conversion reports, and the event's " +
               "Campaigns tab.",
      slides: [],
      videos: []
    }
  ]
};
