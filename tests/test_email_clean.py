"""core/email_clean.py — the ported CRM_Extender stripping pipeline."""

from core.email_clean import CleanedEmail, clean_email

GMAIL_REPLY_HTML = """
<div dir="ltr">Thanks James — let's plan on Tuesday at 2pm.<div><br></div>
<div>I'll send the revised cash-flow sheet before then.</div></div>
<br><div class="gmail_quote"><div dir="ltr" class="gmail_attr">On Mon, Jul 6, 2026 at 9:14 AM James Koran &lt;james@acme.test&gt; wrote:<br></div>
<blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex">Hi Doug,<br>
Can we move our session to Tuesday?<br>Thanks,<br>James</blockquote></div>
"""

OUTLOOK_PLAIN = """Sounds good, see you then.

Bob Mentor
Director | Cleveland Business Mentors
Tel: (216) 555-0100

________________________________
From: James Koran <james@acme.test>
Sent: Monday, July 6, 2026 9:14 AM
To: Bob Mentor <bob.mentor@cbmentors.org>
Subject: Session

Hi Bob, can we meet Tuesday instead?
"""

MOBILE_PLAIN = """Yes that works.

Sent from my iPhone

> On Jul 6, 2026, at 9:14 AM, James Koran <james@acme.test> wrote:
> Can we meet Tuesday?
"""

DISCLAIMER_PLAIN = """Attached is the revised plan for Q3.

CONFIDENTIALITY NOTICE: This e-mail is confidential and intended only for the
use of the individual to whom it is addressed. If you are not the intended
recipient, please notify the sender immediately.
"""

DASH_SIG_PLAIN = """See my notes inline below the second heading.

--
Pat Chen
Founder, Acme Inc
pat@acme.test | www.acme.test
"""


def test_gmail_html_reply_keeps_only_new_text():
    out = clean_email("", GMAIL_REPLY_HTML)
    assert "Tuesday at 2pm" in out.text
    assert "revised cash-flow sheet" in out.text
    assert "wrote:" not in out.text                       # quoted chain removed
    assert "Can we move our session" not in out.html      # NOT in the stored HTML
    assert "Can we move our session" in out.quoted        # …but still on the dataclass
    assert out.snippet.startswith("Thanks James")


def test_outlook_separator_and_signature_stripped():
    out = clean_email(OUTLOOK_PLAIN)
    assert "Sounds good" in out.text
    assert "From:" not in out.text
    assert "Tel:" not in out.text                        # signature block removed
    assert "can we meet tuesday" in out.quoted.lower()   # quoted zone captured


def test_mobile_signature_and_quote_removed():
    out = clean_email(MOBILE_PLAIN)
    assert out.text == "Yes that works."
    assert "iPhone" not in out.text


def test_confidentiality_disclaimer_truncated():
    out = clean_email(DISCLAIMER_PLAIN)
    assert "revised plan for Q3" in out.text
    assert "CONFIDENTIALITY" not in out.text


def test_dash_dash_signature_stripped_but_content_kept():
    out = clean_email(DASH_SIG_PLAIN)
    assert "notes inline" in out.text
    assert "Founder" not in out.text


def test_empty_input():
    out = clean_email("", None)
    assert out == CleanedEmail(text="", quoted="", html="", snippet="")


def test_image_only_mail_gets_placeholder_not_raw_dump():
    out = clean_email("[cid:image001.png@01DC]")
    assert "no new text" in out.text


# The exact live failure (2026-07-11): Gmail plain-text quoting inside an HTML
# body, with the "On ... wrote:" header WRAPPED onto a second line and the
# history quoted with ">" prefixes. The old single-line pattern missed it and
# the whole quoted chain leaked into the author zone.
WRAPPED_QUOTE_PLAIN = (
    "Sounds great, talk soon!\r\n\r\n"
    "On Fri, Jun 26, 2026 at 1:06\u202fAM Douglas Bower <doug.bower@cbmentors.org> \r\n"
    "wrote:\r\n\r\n"
    "> James/Sheila,\r\n>\r\n> It is official.  I am now a member!\r\n"
)


def test_wrapped_on_wrote_header_stripped():
    out = clean_email(WRAPPED_QUOTE_PLAIN)
    assert out.text == "Sounds great, talk soon!"
    assert "James/Sheila" not in out.html


def test_quote_only_reply_gets_placeholder():
    # A reply whose ONLY content is the quoted chain (e.g. an accidental send).
    quote_only = (
        "On Fri, Jun 26, 2026 at 1:06\u202fAM Douglas Bower <doug.bower@cbmentors.org> \r\n"
        "wrote:\r\n\r\n> It is official.\r\n> I am now a member!\r\n"
    )
    out = clean_email(quote_only)
    assert "no new text" in out.text
    assert "official" not in out.html


def test_html_escaped_in_output():
    out = clean_email("Use <b>bold</b> & such.")
    assert "&lt;b&gt;" in out.html and "&amp;" in out.html


# --- outbound mode (the 2026-07-21 "sent emails look cut off" fix) -----------
# Messages OUR user wrote get the light clean: quoted history removed, but the
# inbound signature/valediction heuristics — which truncate authored content —
# are skipped entirely.


def test_outbound_keeps_content_after_early_valediction():
    html = (
        "<p>Hi Mindy,</p><p>Thanks,</p>"
        "<p>I reviewed your business plan and have three suggestions. "
        "Contact our partner at info@cbmentors.org for funding help.</p>"
    )
    out = clean_email("", html, outbound=True)
    assert "three suggestions" in out.text
    assert "info@cbmentors.org" in out.text


def test_outbound_keeps_person_introduction():
    html = (
        "<p>Hi Mindy,</p><p>I want to introduce you to my colleague:</p>"
        "<p>Jane Smith<br>Marketing Consultant<br>jane@example.com</p>"
        "<p>She can help with your social media strategy.</p>"
    )
    out = clean_email("", html, outbound=True)
    assert "Jane Smith" in out.text
    assert "social media strategy" in out.text


def test_outbound_keeps_signature_and_signoff():
    html = (
        "<p>Great meeting today.</p><p>Thanks,</p>"
        "<p>Douglas Bower<br>Mentor, Cleveland Business Mentors</p>"
    )
    out = clean_email("", html, outbound=True)
    assert "Thanks" in out.text
    assert "Douglas Bower" in out.text


def test_outbound_still_strips_quoted_history():
    html = (
        "<div dir='ltr'><p>Sounds good, see you Friday.</p>"
        "<div class='gmail_signature'>Doug Bower<br>Mentor</div></div>"
        "<div class='gmail_quote'>On Thu, Jul 16, 2026 Mindy wrote:<br>"
        "<blockquote>Can we meet Friday instead?</blockquote></div>"
    )
    out = clean_email("", html, outbound=True)
    assert "see you Friday" in out.text
    assert "Doug Bower" in out.text  # own gmail_signature kept on outbound
    assert "meet Friday instead" not in out.text
    assert "meet Friday instead" in out.quoted


def test_outbound_plaintext_strips_on_wrote_tail():
    body = (
        "Sounds great, talk soon!\n\n"
        "On Fri, Jun 26, 2026 at 1:06 AM Mindy Bower <mindy@mindybower.com>\n"
        "wrote:\n\n> Are we still on for Friday?\n"
    )
    out = clean_email(body, outbound=True)
    assert out.text == "Sounds great, talk soon!"


def test_inbound_default_unchanged_strips_signature():
    html = (
        "<p>Great meeting today.</p><p>Thanks,</p>"
        "<p>Douglas Bower<br>Mentor, Cleveland Business Mentors<br>"
        "doug.bower@cbmentors.org</p>"
    )
    out = clean_email("", html)
    assert "Douglas Bower" not in out.text
