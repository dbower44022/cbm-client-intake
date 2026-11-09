# Connecting a chapter website to the chapter applications

**Document:** Runbook: setting up the chapter applications' side of a chapter website
**Version:** 1.0
**Status:** Current
**Owner:** Doug Bower
**Last Updated:** 11-09-26 11:59

The steps a chapter's technical person takes in the chapter applications so that the chapter website, running the Association's chapter connector (the WordPress add-on that places the applications' content into the website's pages), can show the chapter's look, its key pages and its forms. The website's own side (hosting, WordPress, the chapter connector) is the Association's setup runbook, `~/Dropbox/Projects/business-mentors-association/docs/setup-runbook.md`. Design and decisions: `prds/chapter-website-plan.md`.

## Before you start

- A browser signed in to the chapter applications as a **CRM administrator**: only administrators can open System Settings. The steps use crm-test's address, `https://cbm-client-intake-svxs3.ondigitalocean.app`; on another deployment, use its address instead.
- The deployment runs version 0.317.1 or later (its page footer shows the version).
- These values, which the steps call by the names on the left:

  - `WEBSITE-ADDRESS` — The chapter website's address, scheme and host only, such as https://chapter-demo.mentorsassociation.org.
  - `CHAPTER-NAME` — The chapter's full name.
  - `CHAPTER-ABBREVIATION` — Its short form, such as FLBM.
  - `CHAPTER-ADDRESS` — Its mailing address.
  - `CHAPTER-EMAIL` — Its one public contact email address.
  - `CHAPTER-PHONE` — Its public telephone number.
  - `CHAPTER-EIN` — Its employer identification number, written 12-3456789.
  - `PAYMENT-PAGE-ADDRESS` — The https address of its hosted donation page, such as a Stripe Payment Link.
  - `SOCIAL-LINKS` — Label|https://… pairs, comma separated, such as LinkedIn|https://www.linkedin.com/company/example.
  - `COLOUR-BACKGROUND … COLOUR-BORDER` — The eight colours, each #RRGGBB.
  - `FONT-HEADINGS, FONT-BODY` — Two font lists, such as Georgia, serif.
  - `LOGO-FILE, HEADER-FILE` — The logo and the header graphic, PNG, JPEG or WebP, up to 2 MB each.
  - `LINK-NAME, WEBSITE-PAGE-PATH` — Section 8 only: a name for where the link will be posted, and the page's path, such as /mentors/.

Each step that changes a setting can be undone: open the same setting and click **Reset to deployment value**, or see section 9 for the switches.

## Section 1 · In System Settings: name the chapter website

The applications serve the website only at the addresses named here. Do this section first: later switches depend on it.

1. In the browser's address bar, type the applications' address followed by `/setup/`, then press Enter. For crm-test that is the address below.
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/setup/
   ```
   You should see: The System Settings page, with the tabs Settings, Feature readiness, Environment diff, Operations and History. If a sign-in form appears first, sign in with a CRM administrator account. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens System Settings. Every later section starts on this page.

2. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_origins
   ```
   You should see: One row, **Chapter website addresses**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

3. On the **Chapter website addresses** row, click the name **Chapter website addresses**.
   You should see: A dialog titled **Chapter website addresses**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

4. In the **Chapter website addresses** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     WEBSITE-ADDRESS
     ```
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Chapter website addresses** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Names the one website allowed to fetch the key pages' content and to show the forms in frames.

5. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   organization_website_url
   ```
   You should see: One row, **Organisation website**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

6. On the **Organisation website** row, click the name **Organisation website**.
   You should see: A dialog titled **Organisation website**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

7. In the **Organisation website** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     WEBSITE-ADDRESS
     ```
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Organisation website** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The address campaign links to website pages are built on, and the link back from the events pages.

**Checkpoint.** Send back: the two values shown on the Chapter website addresses and Organisation website rows.

## Section 2 · In System Settings: the chapter's details

Each value is set once here, and the website's footer and Donate button read it from here.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   organization_name
   ```
   You should see: One row, **Organisation name**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

2. On the **Organisation name** row, click the name **Organisation name**.
   You should see: A dialog titled **Organisation name**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

3. In the **Organisation name** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-NAME
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Organisation name** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The chapter's name, in the website footer and on every page of the applications.

4. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   organization_abbreviation
   ```
   You should see: One row, **Chapter acronym**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

5. On the **Chapter acronym** row, click the name **Chapter acronym**.
   You should see: A dialog titled **Chapter acronym**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

6. In the **Chapter acronym** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-ABBREVIATION
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Chapter acronym** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The short form of the name.

7. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_postal_address
   ```
   You should see: One row, **Chapter postal address**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

8. On the **Chapter postal address** row, click the name **Chapter postal address**.
   You should see: A dialog titled **Chapter postal address**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

9. In the **Chapter postal address** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-ADDRESS
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Chapter postal address** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The mailing address in the website footer and in personal emails.

10. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_email
   ```
   You should see: One row, **Chapter contact email**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

11. On the **Chapter contact email** row, click the name **Chapter contact email**.
   You should see: A dialog titled **Chapter contact email**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

12. In the **Chapter contact email** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-EMAIL
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Chapter contact email** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The one public contact address the website shows.

13. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_phone
   ```
   You should see: One row, **Chapter telephone**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

14. On the **Chapter telephone** row, click the name **Chapter telephone**.
   You should see: A dialog titled **Chapter telephone**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

15. In the **Chapter telephone** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-PHONE
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Chapter telephone** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The telephone number in the website footer.

16. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_ein
   ```
   You should see: One row, **Employer identification number**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

17. On the **Employer identification number** row, click the name **Employer identification number**.
   You should see: A dialog titled **Employer identification number**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

18. In the **Employer identification number** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     CHAPTER-EIN
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Employer identification number** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The number beside the 501(c)(3) statement in the website footer.

19. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_payment_url
   ```
   You should see: One row, **Donation payment page**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

20. On the **Donation payment page** row, click the name **Donation payment page**.
   You should see: A dialog titled **Donation payment page**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

21. In the **Donation payment page** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     PAYMENT-PAGE-ADDRESS
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Donation payment page** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Where the website's Donate button goes.

22. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   chapter_social_links
   ```
   You should see: One row, **Social media addresses**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

23. On the **Social media addresses** row, click the name **Social media addresses**.
   You should see: A dialog titled **Social media addresses**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

24. In the **Social media addresses** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     SOCIAL-LINKS
     ```
   - **Reason**:
     ```
     Chapter website details
     ```
   You should see: The dialog closes, and the **Social media addresses** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The social media links in the website footer.

**Checkpoint.** Send back: nothing; section 6 checks every value at once.

## Section 3 · In System Settings: the website's colours and fonts

The chapter connector applies these to the whole website. A colour is written #RRGGBB, such as #173B60.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_base
   ```
   You should see: One row, **Colour — background**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

2. On the **Colour — background** row, click the name **Colour — background**.
   You should see: A dialog titled **Colour — background**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

3. In the **Colour — background** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-BACKGROUND
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — background** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

4. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_contrast
   ```
   You should see: One row, **Colour — text**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

5. On the **Colour — text** row, click the name **Colour — text**.
   You should see: A dialog titled **Colour — text**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

6. In the **Colour — text** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-TEXT
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — text** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

7. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_1
   ```
   You should see: One row, **Colour — main brand**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

8. On the **Colour — main brand** row, click the name **Colour — main brand**.
   You should see: A dialog titled **Colour — main brand**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

9. In the **Colour — main brand** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-MAIN
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — main brand** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

10. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_2
   ```
   You should see: One row, **Colour — light brand tint**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

11. On the **Colour — light brand tint** row, click the name **Colour — light brand tint**.
   You should see: A dialog titled **Colour — light brand tint**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

12. In the **Colour — light brand tint** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-TINT
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — light brand tint** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

13. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_3
   ```
   You should see: One row, **Colour — highlight**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

14. On the **Colour — highlight** row, click the name **Colour — highlight**.
   You should see: A dialog titled **Colour — highlight**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

15. In the **Colour — highlight** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-HIGHLIGHT
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — highlight** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

16. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_4
   ```
   You should see: One row, **Colour — muted text**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

17. On the **Colour — muted text** row, click the name **Colour — muted text**.
   You should see: A dialog titled **Colour — muted text**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

18. In the **Colour — muted text** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-MUTED
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — muted text** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

19. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_5
   ```
   You should see: One row, **Colour — light section background**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

20. On the **Colour — light section background** row, click the name **Colour — light section background**.
   You should see: A dialog titled **Colour — light section background**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

21. In the **Colour — light section background** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-SECTION
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — light section background** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

22. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_color_accent_6
   ```
   You should see: One row, **Colour — borders**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

23. On the **Colour — borders** row, click the name **Colour — borders**.
   You should see: A dialog titled **Colour — borders**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

24. In the **Colour — borders** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     COLOUR-BORDER
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Colour — borders** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

25. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_font_heading
   ```
   You should see: One row, **Font — headings**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

26. On the **Font — headings** row, click the name **Font — headings**.
   You should see: A dialog titled **Font — headings**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

27. In the **Font — headings** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     FONT-HEADINGS
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Font — headings** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

28. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_font_body
   ```
   You should see: One row, **Font — body text**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

29. On the **Font — body text** row, click the name **Font — body text**.
   You should see: A dialog titled **Font — body text**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

30. In the **Font — body text** dialog, click the **Value** box, select anything already in it, and type or paste the value below. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Value**:
     ```
     FONT-BODY
     ```
   - **Reason**:
     ```
     Chapter website look
     ```
   You should see: The dialog closes, and the **Font — body text** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Sets one of the website's colours or fonts; the website and its framed forms follow it.

**Checkpoint.** Send back: nothing; section 6 checks every value at once.

## Section 4 · In System Settings: the logo and the header graphic

The images are stored by the applications, so the chapter needs no other place to host them.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and press Delete, so the box is empty. Scroll to the heading **Website**, and below its table, to the panel **Website images**.
   You should see: Two cards, **Logo** and **Header graphic**, each with an **Upload…** and a **Remove** button. If not, stop and tell the central support organization exactly what you see.
   What it does: Finds the image uploads.

2. On the **Logo** card, click **Upload…**, choose the file LOGO-FILE in the window that opens, and click **Open**.
   You should see: Within a second, the picture on the Logo card and the line "Uploaded. The website shows it within a few minutes." If the card shows a message instead, it names what is wrong with the file (only PNG, JPEG or WebP up to 2 MB is accepted): save the file accordingly and try again. If not, stop and tell the central support organization exactly what you see.
   What it does: Uploads the logo the website shows beside its name.

3. On the **Header graphic** card, click **Upload…**, choose the file HEADER-FILE in the window that opens, and click **Open**.
   You should see: Within a second, the picture on the Header graphic card and the line "Uploaded. The website shows it within a few minutes." If not, stop and tell the central support organization exactly what you see.
   What it does: Uploads the graphic shown under the website's header.

**Checkpoint.** Send back: nothing; section 6 checks both images.

## Section 5 · In System Settings: switch on the connection and the key pages

Our Partners, Our Sponsors and Client Stories cannot be switched on yet: System Settings refuses them and says why.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_api
   ```
   You should see: One row, **Chapter website connection**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

2. On the **Chapter website connection** row, click the name **Chapter website connection**.
   You should see: A dialog titled **Chapter website connection**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

3. In the **Chapter website connection** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Chapter website connection** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Switches on the addresses the chapter connector reads.

4. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_page_mentors
   ```
   You should see: One row, **Key page — Find a Mentor**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

5. On the **Key page — Find a Mentor** row, click the name **Key page — Find a Mentor**.
   You should see: A dialog titled **Key page — Find a Mentor**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

6. In the **Key page — Find a Mentor** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Key page — Find a Mentor** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Shows the key page and its menu entry on the website.

7. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_page_events
   ```
   You should see: One row, **Key page — Workshops and Events**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

8. On the **Key page — Workshops and Events** row, click the name **Key page — Workshops and Events**.
   You should see: A dialog titled **Key page — Workshops and Events**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

9. In the **Key page — Workshops and Events** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Key page — Workshops and Events** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Shows the key page and its menu entry on the website.

10. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_page_recordings
   ```
   You should see: One row, **Key page — Recordings**, under the heading Website. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

11. On the **Key page — Recordings** row, click the name **Key page — Recordings**.
   You should see: A dialog titled **Key page — Recordings**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

12. In the **Key page — Recordings** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Key page — Recordings** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Shows the key page and its menu entry on the website.

**Checkpoint.** Send back: nothing; section 6 checks the switches.

## Section 6 · In the browser: check what the website receives

This address is what the chapter connector reads. A value missing here never reaches the website.

1. In a new browser tab, type the applications' address followed by `/api/website/settings`, then press Enter. For crm-test that is the address below.
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/api/website/settings
   ```
   You should see: A page of text beginning `{"version":1`. It holds every colour and font from section 3, the chapter's details from section 2 under `"chapter"`, a `logoUrl` and a `headerImage` that each begin with the applications' address, and `"mentors":true`, `"events":true` and `"recordings":true` under `"pages"`. The answer may be a minute old: if a value you saved in the last minute is missing, wait one minute and press F5. If not, stop and tell the central support organization exactly what you see.
   What it does: Shows exactly what the chapter connector receives.

**Checkpoint.** Send back: any value from sections 2 to 5 that is missing or different.

## Section 7 · In System Settings: forms in frames and the newsletter form

Warning: once Forms in website frames is on, every website that frames a form must be named in section 1, or its forms go blank. Cleveland's own website frames three forms. To undo, set the switch to Off as in section 9.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   form_framing
   ```
   You should see: One row, **Forms in website frames**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

2. On the **Forms in website frames** row, click the name **Forms in website frames**.
   You should see: A dialog titled **Forms in website frames**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

3. In the **Forms in website frames** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Forms in website frames** row shows the new value and the chip **Override**. From now on, a form framed by any website not named in section 1 shows a blank frame. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Only the chapter website may show the forms in a frame; the frames fit the forms and take the website's look.

4. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   newsletter_form
   ```
   You should see: One row, **Newsletter signup form**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

5. On the **Newsletter signup form** row, click the name **Newsletter signup form**.
   You should see: A dialog titled **Newsletter signup form**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

6. In the **Newsletter signup form** dialog, click the **Value** list and choose **On**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Chapter website
     ```
   You should see: The dialog closes, and the **Newsletter signup form** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Opens the newsletter signup form at /newsletter/.

**Checkpoint.** Send back: nothing; the chapter website's own setup checks the framed forms.

## Section 8 · In Marketing Management: a campaign link to a website page

Optional; do it when a campaign is to send visitors to a website page rather than straight to a form.

1. In the browser, type the applications' address followed by `/campaigns/`, then press Enter. For crm-test that is the address below.
   ```
   https://cbm-client-intake-svxs3.ondigitalocean.app/campaigns/
   ```
   You should see: Marketing Management, open on the Leads tab. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens Marketing Management.

2. In Marketing Management, click the **Campaigns** tab, then click the name of the campaign the link belongs to.
   You should see: The campaign's own page, with its tabs. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the campaign.

3. On the campaign's page, click the **Links** tab, then click **+ New link**.
   You should see: A dialog titled **New link**, with the boxes Name and Opens. If not, stop and tell the central support organization exactly what you see.
   What it does: Starts a link.

4. In the **New link** dialog, fill in the fields below, then click **Create**.
   - **Name**:
     ```
     LINK-NAME
     ```
   - **Opens**:
     ```
     A page on the chapter website
     ```
   - **Page on the chapter website (its path, such as /mentors/)**:
     ```
     WEBSITE-PAGE-PATH
     ```
   You should see: The dialog closes, and the Links tab lists the link, with its destination reading **Chapter website page** followed by WEBSITE-PAGE-PATH and a short link beginning with the applications' address and `/c/`. If a message says links to the chapter website are not switched on, section 5's first setting is Off. If not, stop and tell the central support organization exactly what you see.
   What it does: Makes a campaign link that opens a website page and credits the campaign on any form the visitor fills in on that visit.

**Checkpoint.** Send back: the link's short link from section 8, step 4.

## Section 9 · In System Settings: switch everything off again

Only when undoing. Each switch is independent and takes effect within a minute. Values from sections 1 to 4 are kept.

1. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   website_api
   ```
   You should see: One row, **Chapter website connection**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

2. On the **Chapter website connection** row, click the name **Chapter website connection**.
   You should see: A dialog titled **Chapter website connection**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

3. In the **Chapter website connection** dialog, click the **Value** list and choose **Off**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Undo chapter website
     ```
   You should see: The dialog closes, and the **Chapter website connection** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Stops serving the website; the website keeps showing its last copy.

4. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   form_framing
   ```
   You should see: One row, **Forms in website frames**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

5. On the **Forms in website frames** row, click the name **Forms in website frames**.
   You should see: A dialog titled **Forms in website frames**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

6. In the **Forms in website frames** dialog, click the **Value** list and choose **Off**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Undo chapter website
     ```
   You should see: The dialog closes, and the **Forms in website frames** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: Any website may frame the forms again, as before.

7. On the Settings tab of the System Settings page, click the **Filter settings…** box, select anything already in it, and type the text below.
   ```
   newsletter_form
   ```
   You should see: One row, **Newsletter signup form**, under the heading Features. If not, stop and tell the central support organization exactly what you see. If the row already shows exactly the value the next steps give, skip those two steps.
   What it does: Finds the setting.

8. On the **Newsletter signup form** row, click the name **Newsletter signup form**.
   You should see: A dialog titled **Newsletter signup form**. If not, stop and tell the central support organization exactly what you see.
   What it does: Opens the setting.

9. In the **Newsletter signup form** dialog, click the **Value** list and choose **Off**. Click the **Reason** box and type the reason below. Leave **Temporary — remind me to review it** unticked and both boxes under **Roll out to specific teams or people only** empty. Click **Save**.
   - **Reason**:
     ```
     Undo chapter website
     ```
   You should see: The dialog closes, and the **Newsletter signup form** row shows the new value and the chip **Override**. If a message says the value is not valid, it names the reason: correct the value and click Save again. If anything else appears, stop and tell the central support organization exactly what you see.
   What it does: The newsletter form answers 404.

**Checkpoint.** Send back: which switches were set to Off.

---

## Change log

| Version | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-09-26 11:59 | Claude (Claude Code) | First version, for v0.317.1: pieces A to E of `prds/chapter-website-plan.md`. |
