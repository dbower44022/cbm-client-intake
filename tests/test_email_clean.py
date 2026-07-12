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
