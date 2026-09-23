# Stage 8 — Fill in the chapter information form

**Version:** 0.6  
**Last Updated:** 09-23-26 12:20  
**Generated from** `steps/stage-08.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

The chapter information form holds the roughly forty answers that differ from one chapter to the next: its name, its addresses, its Google details and its feature switches. Everything after this stage is built from the form, so a wrong or missing answer here becomes a fault in every later stage. The form is a web page: each question says what it means, where to find the answer and what goes wrong if the answer is wrong, and the answers are saved as they are typed.

**Who:** The chapter's setup contact answers the questions about the chapter. The central support organization answers the technical ones. Both work in the same page, and each can see what is still waiting for the other.  
**Time:** About an hour of answering, once the website, the policy documents and Google Workspace exist. It does not have to be done in one sitting.  
**When this stage is done:** Building the CRM (stage 9). Nothing after this stage can start until the form is complete and reviewed, and everything after it becomes routine once it is.

**Before you start:**

- The agreement is signed (step 2.6)
- Google Workspace is set up (stage 4)
- The website is published and the four policy documents have their addresses (stages 6 and 7). A question whose answer does not exist yet can be marked "not known yet" and answered later, except the four policy addresses

**Steps in this stage:**

- 8.1 Obtain the blank form
- 8.2 Fill in the chapter's name and identity
- 8.3 Fill in the web addresses
- 8.4 Fill in the Google details
- 8.5 Fill in the CRM details
- 8.6 Decide every feature switch
- 8.7 List the secrets by name
- 8.8 Put the chapter's secrets into the store
- 8.9 Review the completed form
- 8.10 Store the form where the central support organization can reach it

---

## 8.1 Obtain the blank form

**Why:** Everyone works from one page, built from this guide, so the questions can never fall behind the software.

**Who:** The chapter and the central support organization — the central support organization publishes the page; the chapter's setup contact opens it

**Finish first:**

- step 2.6 Sign the agreement

**Do this:**

1. The central support organization: in a Claude Code session in the folder ~/Dropbox/Projects/cbm-client-intake, type this request, with the chapter's name in place of CHAPTER-NAME:
   - Build and publish the chapter information page for CHAPTER-NAME with scripts/chapter_form/build_page.py.
   *You should see:* A link to a page titled with the chapter's short name followed by Chapter Information.
2. Open the link. In the page's Share menu, change the access so anyone with the link can open the page. A published page starts private, and a visitor who is not signed in to claude.ai is shown a sign-in page until this is changed.
   *You should see:* The Share menu showing the page open to anyone with the link.
3. Open the link in a private browser window, where you are not signed in.
   *You should see:* The page itself, not a sign-in page.
4. Send the link to the chapter's setup contact, with this guide's stage 8 page.
5. The chapter's setup contact: open the link.
   *You should see:* The page, with a line at the top reading how many questions are answered, and each question marked either For the chapter or For central support.

**Done when:** The chapter has the current blank form and knows who fills in each part.

**How to check:** The setup contact opens the page, types an answer into one question, reloads the page, and the answer is still there, marked saved in this browser.

**If it didn't work:** If the setup contact sees a sign-in page, the page is still private; change its access in the Share menu. If the page says the browser is not keeping answers, the setup contact uses Copy all answers before closing it, or answers on a call with the central support organization typing.

**What usually goes wrong:** Leaving the page private. It looks fine to the person who published it, because they are signed in, and every one else sees a sign-in page. The setup contact needs no claude.ai account once the page is open to anyone with the link (confirmed 09-23-26).

---

## 8.2 Fill in the chapter's name and identity

**Why:** The chapter's name appears on every page the software shows, and the short label names its servers and secrets.

**Who:** The chapter

**Finish first:**

- step 1.1 Choose the chapter's name
- step 8.1 Obtain the blank form

**Do this:**

1. Answer every question in the section "Fill in the chapter's name and identity" on the page. Each question is explained below, and the same explanation is beside it on the page.
   *You should see:* Every question in the section marked as saved.

**The questions in this step:**

- **Chapter name** (`chapter.name`) — answered by the chapter; required.
  - *What it is:* The chapter's name, exactly as it should appear on every page, email and screen the software shows. Capital letters count.
  - *Where to find it:* The chapter's legal name from step 1.1, or the trading name the board chose.
  - *If it is wrong:* Every page title, page footer and email shows the wrong name until it is corrected and the applications are deployed again.
  - *Example:* Boston Business Mentors
- **Short label** (`chapter.slug`) — answered by the chapter; required.
  - *What it is:* One short lower-case word that names the chapter's server, applications and secrets. Letters, digits and hyphens only, starting with a letter.
  - *Where to find it:* Choose it now. The city's name is usual.
  - *If it is wrong:* The label becomes part of the names of the chapter's server and applications. Changing it after stage 9 means renaming them.
  - *Example:* boston
- **Time zone** (`chapter.timezone`) — answered by the chapter; required.
  - *What it is:* The time zone the chapter works in. America/New_York is Eastern time.
  - *Where to find it:* Where the chapter operates.
  - *If it is wrong:* Dates on birthday greetings, mentor assignments and the public events page come out a day off. The software supports only Eastern time today (work list item 17), so any other choice must be raised with the central support organization before stage 9.
  - *Recommended:* America/New_York
- **Currency** (`chapter.currency`) — answered by the chapter; required.
  - *What it is:* The currency of every money amount in the CRM, such as grants and contributions.
  - *Where to find it:* US dollars for every chapter today.
  - *If it is wrong:* The CRM refuses to save any amount.
  - *Recommended:* USD
- **Language and number format** (`chapter.locale`) — answered by the chapter; required.
  - *What it is:* The language the CRM's screens use, and how it writes dates and numbers.
  - *Where to find it:* US English for every chapter today.
  - *If it is wrong:* The CRM's screens and dates appear in the wrong language or format.
  - *Recommended:* en_US

**Done when all of these are true:**

- The chapter name is filled in.
- The short label is filled in.
- The time zone is filled in.
- The currency is filled in.
- The language is filled in.

**How to check:** The name matches the legal name, or the trading name the board chose, letter for letter.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** The time zone. A chapter outside the Eastern United States gets wrong dates on birthday greetings, assignment dates and the public events page, and nothing reports an error.

---

## 8.3 Fill in the web addresses

**Why:** The software links to the website, the help documentation and the four policy documents, and a broken link on the consent box is a legal problem.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 6.2 Publish the website
- step 6.7 Decide where the chapter's help documentation lives
- step 7.6 Record the four web addresses
- step 8.1 Obtain the blank form

**Do this:**

1. Answer every question in the section "Fill in the web addresses" on the page. Copy each address from a browser's address bar rather than typing it.
   *You should see:* Every question in the section marked as saved, or marked not known yet where that is allowed.
2. The central support organization: in a terminal, run the line below once for each address in the section except the applications' address, with the address in place of ADDRESS:
   - curl -sI ADDRESS
   *You should see:* A first line of HTTP/2 200 for every one.

**The questions in this step:**

- **Website address** (`web.website_base_url`) — answered by the chapter; required.
  - *What it is:* The home page address of the chapter's public website.
  - *Where to find it:* The website published in step 6.2. Open it in a browser and copy the address bar.
  - *If it is wrong:* The link back to the website and the website menu on the software's public pages point somewhere else.
  - *Example:* https://bbmentors.org
- **Applications' address** (`web.app_base_url`) — answered by the central support organization; required.
  - *What it is:* The address the chapter's applications will have. It does not open yet; it starts working at step 11.10.
  - *Where to find it:* https://apps. followed by the chapter's domain, unless the chapter and the central support organization agree another name.
  - *If it is wrong:* Links in emails the software sends point to the wrong place, and signing in can fail because the software only trusts its own address.
  - *Example:* https://apps.bbmentors.org
- **Help documentation address** (`web.docs_site_url`) — answered by the chapter; may be marked not known yet.
  - *What it is:* The address of the chapter's help and documentation site, linked from the applications' home page and the CRM's menu.
  - *Where to find it:* The decision in step 6.7. If the chapter has no documentation site yet, mark this not known yet.
  - *If it is wrong:* The Documentation link leads nowhere. Marked not known yet, the link is simply left out.
  - *Example:* https://docs.bbmentors.org
- **Client code of conduct address** (`web.policy_client_conduct_url`) — answered by the chapter; required.
  - *What it is:* The address of the chapter's client code of conduct. Every public application form links to it from its consent box.
  - *Where to find it:* The policy documents published in stage 7.
  - *If it is wrong:* Applicants agree to a document that is not the chapter's, which is a legal problem, not a cosmetic one.
- **Mentor code of ethics address** (`web.policy_mentor_ethics_url`) — answered by the chapter; required.
  - *What it is:* The address of the chapter's mentor code of ethics. The volunteer application form links to it from its consent box.
  - *Where to find it:* The policy documents published in stage 7.
  - *If it is wrong:* Volunteers agree to a document that is not the chapter's.
- **Terms of use address** (`web.policy_terms_url`) — answered by the chapter; required.
  - *What it is:* The address of the chapter's terms of use, linked from every public form.
  - *Where to find it:* The policy documents published in stage 7.
  - *If it is wrong:* Applicants agree to terms that are not the chapter's.
- **Privacy policy address** (`web.policy_privacy_url`) — answered by the chapter; required.
  - *What it is:* The address of the chapter's privacy policy, linked from every public form.
  - *Where to find it:* The policy documents published in stage 7.
  - *If it is wrong:* Applicants are shown a privacy policy that is not the chapter's, which is a legal exposure.
- **Colour file address** (`web.chapter_tokens_url`) — answered by the chapter; may be marked not known yet.
  - *What it is:* The address of a small file that sets the chapter's colours on the software's pages.
  - *Where to find it:* The colour file published in step 6.5. Most chapters start without one; mark this not known yet.
  - *If it is wrong:* The pages keep the standard colours. Nothing breaks.

**Done when all of these are true:**

- The application address is filled in.
- The website address is filled in.
- The events page address is left empty, so the software uses its own events page.
- The documentation address is filled in.
- The colour file address is filled in.
- The four policy addresses are filled in.

**Note:** The events page address is not asked. Left empty, it means the applications' own events page, APP-ADDRESS/webinars/, which is what every chapter now uses. The documentation and colour file addresses count as filled in when they are marked not known yet.

**How to check:** Every address, opened in a private browser window, shows the right page.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A policy address that does not load. The public application form links to all four policies from its consent box.

---

## 8.4 Fill in the Google details

**Why:** Mail, calendars, documents and mentor mailboxes all run through the chapter's Google Workspace, and each needs an exact address.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 4.1 Confirm the chapter will hold its own Google Workspace
- step 4.7 Create the shared operations mailbox
- step 4.8 Create the alert sending mailbox
- step 4.9 Decide who receives the system's warning messages
- step 4.10 Create the members group
- step 8.1 Obtain the blank form

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Answer every question in the section "Fill in the Google details" on the page, copying each address from the Google Workspace admin console at admin.google.com. The Zoom questions appear only once the webinar question in step 8.6 is answered yes.
   *You should see:* Every question in the section marked as saved, apart from the shared drive, which step 10.5 answers.
2. The central support organization: in the Google Workspace admin console, open Users and find the shared operations mailbox and the alert sending mailbox.
   *You should see:* Both listed as users with a licence. Neither is a group.

**The questions in this step:**

- **Staff email domain** (`google.primary_domain`) — answered by the chapter; required.
  - *What it is:* The part after the @ in the chapter's staff email addresses.
  - *Where to find it:* The Google Workspace admin console, under Account, then Domains.
  - *If it is wrong:* Email between the chapter's own people is treated as client email and filed on client records.
  - *Example:* bbmentors.org
- **Shared operations mailbox** (`google.ops_mailbox`) — answered by the chapter; required.
  - *What it is:* The shared mailbox where public enquiries arrive. The software reads it and sends replies from it.
  - *Where to find it:* The mailbox created in step 4.7. It must be a user with a licence, never a group or an alias.
  - *If it is wrong:* A group or alias makes reading and sending fail with an error that does not name the cause. If any other system reads the same mailbox, each one gets about half the messages.
  - *Example:* info@bbmentors.org
- **Alert sending mailbox** (`google.alert_email_from`) — answered by the chapter; required.
  - *What it is:* The mailbox the software sends its warning messages from.
  - *Where to find it:* The mailbox created in step 4.8. It must be a user with a licence, never a group.
  - *If it is wrong:* A group is refused, and the refusal reads as though the software has no permission at all.
  - *Example:* alerts@bbmentors.org
- **Alert receiving address** (`google.alert_email_to`) — answered by the chapter; required.
  - *What it is:* Who receives the software's warning messages. It may be a group.
  - *Where to find it:* The decision in step 4.9.
  - *If it is wrong:* Warnings about failed submissions reach nobody.
  - *Example:* support@bbmentors.org
- **Members group** (`google.members_group`) — answered by the chapter; may be marked not known yet.
  - *What it is:* The Google group every member of the chapter belongs to. A new mentor's mailbox is added to it automatically.
  - *Where to find it:* The group created in step 4.10. Mark not known yet if the chapter has none; the software then skips adding mentors to a group.
  - *If it is wrong:* New mentors are added to the wrong group, or to none.
  - *Example:* allmembers@bbmentors.org
- **Mentor email domain** (`google.mentor_email_domain`) — answered by the chapter; required.
  - *What it is:* The domain the software creates mentors' mailboxes and CRM sign-ins on, as firstname.lastname@ this domain. Usually the same as the staff email domain.
  - *Where to find it:* The Google Workspace admin console, under Account, then Domains.
  - *If it is wrong:* Mentors get addresses on a domain the chapter does not own, and their mailboxes cannot be created.
  - *Example:* bbmentors.org
- **Google administrator the software acts as** (`google.delegated_admin`) — answered by the chapter; required.
  - *What it is:* A Google Workspace administrator account. The software acts as this account when it checks and creates mentors' mailboxes.
  - *Where to find it:* The chapter's own administrator account from step 4.5.
  - *If it is wrong:* Checking and creating mentors' mailboxes fails, so new mentors are left without one.
  - *Example:* admin@bbmentors.org
- **Shared drive identifier** (`google.shared_drive_id`) — answered by the central support organization; may be marked not known yet; filled in at step 10.5.
  - *What it is:* The identifier of the shared drive where the software files each record's documents.
  - *Where to find it:* Step 10.5 creates the drive and writes its identifier here. It is the part of the drive's web address after /drive/folders/. Leave it until then.
  - *If it is wrong:* Documents cannot be filed. The settings generator refuses to switch document filing on without it.
- **Zoom webinar host address** (`google.zoom_host_email`) — answered by the chapter; required; asked only for a chapter that runs Zoom webinars.
  - *What it is:* The Zoom user that hosts the chapter's public webinars.
  - *Where to find it:* The Zoom account set up in step 5.5.
  - *If it is wrong:* Webinars are created under Cleveland's host, which the chapter's Zoom app cannot reach.
  - *Example:* webinars@bbmentors.org
- **Zoom app account identifier** (`zoom.account_id`) — answered by the central support organization; required; asked only for a chapter that runs Zoom webinars.
  - *What it is:* The account identifier of the chapter's Zoom app, which the software uses to create webinars.
  - *Where to find it:* The Zoom app created in step 5.5, on its App Credentials screen.
  - *If it is wrong:* Creating webinars fails.
- **Zoom app client identifier** (`zoom.client_id`) — answered by the central support organization; required; asked only for a chapter that runs Zoom webinars.
  - *What it is:* The client identifier of the chapter's Zoom app. Its secret is never typed here; it goes in the vault.
  - *Where to find it:* The Zoom app created in step 5.5, on its App Credentials screen.
  - *If it is wrong:* Creating webinars fails.

**Done when all of these are true:**

- The main domain is filled in.
- The shared operations mailbox is filled in.
- The alert sending address is filled in.
- The alert receiving address is filled in.
- The members group is filled in.
- The mentor email domain is filled in.

**Note:** The members group counts as filled in when it is marked not known yet. The shared drive identifier is filled in at step 10.5, not here.

**How to check:** Each mailbox named on the form is listed as a mailbox, with a licence, in the Google Workspace admin console.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Writing a group where a mailbox is needed. The alert sending address and the shared operations mailbox must both be real licensed mailboxes. A group fails later, with an error that does not name the cause.

---

## 8.5 Fill in the CRM details

**Why:** The CRM has its own name, sending name, sending address and logo, and anything it sends directly carries them.

**Who:** The central support organization

**Finish first:**

- step 6.6 Produce the chapter's logo image
- step 8.1 Obtain the blank form

**Do this:**

1. Answer every question in the section "Fill in the CRM details" on the page.
   *You should see:* Every question in the section marked as saved.

**The questions in this step:**

- **CRM address** (`crm.base_url`) — answered by the central support organization; required.
  - *What it is:* The address of the chapter's CRM. It does not open yet; it starts working at step 9.6.
  - *Where to find it:* https://crm. followed by the chapter's domain, unless agreed otherwise.
  - *If it is wrong:* The applications cannot reach the CRM, and nothing works.
  - *Example:* https://crm.bbmentors.org
- **Name shown inside the CRM** (`crm.application_name`) — answered by the central support organization; required.
  - *What it is:* The name the CRM shows at the top of its own screens.
  - *Where to find it:* Usually the chapter name from step 8.2.
  - *If it is wrong:* The CRM's screens show the wrong name.
  - *Example:* Boston Business Mentors
- **Sending name for the CRM's own emails** (`crm.outbound_from_name`) — answered by the central support organization; required.
  - *What it is:* The sender name on email the CRM sends by itself, such as password resets.
  - *Where to find it:* Usually the chapter name from step 8.2.
  - *If it is wrong:* Those emails arrive under the wrong name.
  - *Example:* Boston Business Mentors
- **Sending address for the CRM's own emails** (`crm.outbound_from_address`) — answered by the central support organization; required.
  - *What it is:* The address email the CRM sends by itself comes from.
  - *Where to find it:* Usually the shared operations mailbox from step 8.4.
  - *If it is wrong:* Password resets and other CRM emails bounce or land in spam.
  - *Example:* info@bbmentors.org
- **Logo file name** (`crm.logo_file`) — answered by the central support organization; may be marked not known yet.
  - *What it is:* The file name of the chapter's logo, shown on the CRM's sign-in screen and menu.
  - *Where to find it:* The logo from step 6.6. No build script sets the logo yet (work list G1, item 2); it is uploaded by hand in the CRM.
  - *If it is wrong:* The CRM shows no logo. Nothing else is affected.
  - *Example:* boston-logo.png

**Done when all of these are true:**

- The CRM address is filled in.
- The name shown inside the CRM is filled in.
- The sending name is filled in.
- The sending address is filled in.
- The logo file is filled in.

**How to check:** The section is complete, and the sending address is a real mailbox.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 8.6 Decide every feature switch

**Why:** Each switch turns a part of the software on or off, and a switch left blank gives a chapter behaviour nobody chose.

**Who:** The chapter and the central support organization — the chapter answers the three questions about what it will do; the central support organization confirms the rest

**Finish first:**

- step 8.2 Fill in the chapter's name and identity
- step 8.3 Fill in the web addresses
- step 8.4 Fill in the Google details
- step 8.5 Fill in the CRM details

**Do this:**

1. The chapter's setup contact: answer the three switch questions marked For the chapter.
   *You should see:* The three marked as saved.
2. The central support organization: check the recommended answer on each remaining switch, change any that should differ, and save each one. The page's button Use recommended answers gives every switch marked For central support that is not yet answered its recommended answer; it never changes a switch already answered or one marked For the chapter.
   *You should see:* Every switch marked as saved. None left blank.

**The questions in this step:**

- **Publish workshops and webinars on the public events page?** (`flags.events_public_api`) — answered by the chapter; required.
  - *What it is:* Whether the applications' public page lists the chapter's upcoming workshops and recorded webinars, with sign-up.
  - *Where to find it:* The chapter's own plan. It can be switched on later.
  - *If it is wrong:* Switched on with nothing published, the page is simply empty.
  - *Recommended:* no
- **Run public webinars through the chapter's own Zoom account?** (`flags.zoom_events`) — answered by the chapter; required.
  - *What it is:* Whether the software creates the chapter's public webinars in Zoom. Answering yes shows three Zoom questions in the Google details section.
  - *Where to find it:* Whether step 5.5 set up a Zoom account for webinars.
  - *If it is wrong:* Switched on without a working Zoom app, creating a webinar fails.
  - *Recommended:* no
- **Create a Google mailbox automatically for each new mentor?** (`flags.google_create_mailbox`) — answered by the chapter; required.
  - *What it is:* Whether the software creates a mentor's Google mailbox when their application is accepted. Each mailbox takes a paid Google licence.
  - *Where to find it:* The chapter's own decision about licence costs.
  - *If it is wrong:* Switched off, someone creates each mentor's mailbox by hand before the mentor can be given a CRM sign-in.
  - *Recommended:* yes
- **Read and file email** (`flags.gmail_sync`) — answered by the central support organization; required.
  - *What it is:* The software reads the shared operations mailbox and mentors' mail, and files messages on the right records.
  - *Where to find it:* On for every chapter, because every chapter has its own Google Workspace. It needs stage 10 finished before step 11.2; the settings generator refuses otherwise.
  - *If it is wrong:* Switched off, enquiries sent to the shared mailbox never appear in the software.
  - *Recommended:* yes
- **Put mentoring sessions on Google calendars** (`flags.gcal_events`) — answered by the central support organization; required.
  - *What it is:* A scheduled session is put on the mentor's Google calendar with the client invited.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, mentors add every session to their calendars by hand.
  - *Recommended:* yes
- **File documents on the shared drive** (`flags.gdrive_docs`) — answered by the central support organization; required.
  - *What it is:* Documents attached to records are kept on the chapter's shared drive.
  - *Where to find it:* On for every chapter. It needs the shared drive identifier from step 10.5.
  - *If it is wrong:* Switched off, the Documents tab on records cannot store anything.
  - *Recommended:* yes
- **Account the shared drive is used as** (`flags.gdrive_identity`) — answered by the central support organization; required.
  - *What it is:* The software uses the shared drive as its own machine account, never as a person.
  - *Where to find it:* Always service.
  - *If it is wrong:* Nothing else is supported.
  - *Recommended:* service
- **Check a mentor's mailbox exists before creating their sign-in** (`flags.google_directory_check`) — answered by the central support organization; required.
  - *What it is:* Before a mentor gets a CRM sign-in, the software confirms their Google mailbox exists, so the welcome email does not bounce.
  - *Where to find it:* On for every chapter. Creating mailboxes automatically needs it on.
  - *If it is wrong:* Switched off, a mentor can be given a sign-in whose welcome email bounces.
  - *Recommended:* yes
- **Create mentors' CRM sign-ins** (`flags.mentor_provision_users`) — answered by the central support organization; required.
  - *What it is:* The software creates a CRM sign-in when a mentor is approved.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, every mentor's sign-in is created by hand.
  - *Recommended:* yes
- **Analytics pages** (`flags.analytics_enabled`) — answered by the central support organization; required.
  - *What it is:* The reporting dashboards in the applications.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, the dashboards are missing.
  - *Recommended:* yes
- **Events page for staff** (`flags.events_enabled`) — answered by the central support organization; required.
  - *What it is:* The staff page for creating and managing workshops and webinars.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, events cannot be managed.
  - *Recommended:* yes
- **Quick add for partners and funders** (`flags.record_quick_add`) — answered by the central support organization; required.
  - *What it is:* Staff can add a partner or funder from its list, without the public form.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, partners and funders arrive only through the public forms.
  - *Recommended:* yes
- **System Settings page** (`flags.setup_enabled`) — answered by the central support organization; required.
  - *What it is:* The administrators' page for changing the applications' settings without a redeployment.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, every settings change needs the central support organization to redeploy.
  - *Recommended:* yes
- **Deliver submissions in the background** (`flags.async_delivery`) — answered by the central support organization; required.
  - *What it is:* A public form is answered at once, and the background worker delivers it to the CRM, retrying if the CRM is down.
  - *Where to find it:* On for every chapter.
  - *If it is wrong:* Switched off, a CRM outage loses the applicant's wait time and can show them an error.
  - *Recommended:* yes
- **Practice mode with no CRM** (`flags.espo_dry_run`) — answered by the central support organization; required.
  - *What it is:* Runs the applications without writing to any CRM. Only for the development copy.
  - *Where to find it:* Always off for a chapter.
  - *If it is wrong:* Switched on, nothing a chapter does is saved in its CRM.
  - *Recommended:* no
- **Take each release automatically** (`flags.deploy_on_push`) — answered by the central support organization; required.
  - *What it is:* The applications follow the release branch and update themselves when a release is cut (step 11.9).
  - *Where to find it:* On for every chapter. The settings generator refuses the development branch.
  - *If it is wrong:* Switched off, the chapter falls behind every release until someone updates it by hand.
  - *Recommended:* yes

**Done when:** Each switch has been deliberately set to on or off, and the branch the application follows is recorded as the release branch rather than the development branch.

**Note:** Until 09-23-26 the starting values switched the Google features off until each check in stage 11 passed. The background worker reads its mail switches only when it starts, so a switch turned on later at the settings page never reached it. The switches are now decided here and go into the deployment at step 11.2.

**How to check:** No switch on the page is blank.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A switch in the software that the form does not list. Until 09-18-26 the blank form was missing five switches the trial chapter needed, and it can fall behind again whenever the software gains one.

---

## 8.7 List the secrets by name

**Why:** Each secret needs a named holder before it exists, so that none is ever held by one person alone.

**Who:** The central support organization

**Finish first:**

- step 8.6 Decide every feature switch

**Do this:**

1. Nothing to type. The page lists the secrets the chapter will have, by name only, and the values file written in step 8.10 includes the list. A chapter that answered yes to webinars in step 8.6 has an eighth, ZOOM_CLIENT_SECRET.
   - ESPO_API_KEY — the CRM key the applications use. Created in step 9.17.
   - ESPO_PROVISION_USERNAME — the name of the administrator account that creates logins. Created in step 9.18.
   - ESPO_PROVISION_PASSWORD — that account's password. Created in step 9.18.
   - DATABASE_URL — the database address. Held by the hosting platform, which supplies it to the application (step 11.4). No person holds it, and it never goes in the vault.
   - SESSION_SECRET — created in step 11.1.
   - APP_ENCRYPTION_KEY — the encryption key for stored data. Created in step 11.2, and never changed afterwards.
   - GOOGLE_SERVICE_ACCOUNT_JSON — the Google key. Created in step 10.2.
   *You should see:* The section The secrets on the page, listing these names:
2. Never type a secret's value into the page. The page is not a secrets store.

**Done when all of these are true:**

- All seven are listed by name with the holder named beside each.
- The video meeting app's secret is listed too, for a chapter that runs webinars.
- No secret value is written on the form.

**Note:** Seven, not six: besides the six the planning documents name, the applications use an encryption key for stored data that the settings generator creates on first run. Changing it later destroys the data it protects, so it is permanent from the moment it exists. The holder of every secret is the chapter's Operations vault (step 8.8).

**How to check:** The page lists seven names, or eight for a webinar chapter, and no values.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Listing six and missing the encryption key. Changing that key later makes every stored secret permanently unreadable.

---

## 8.8 Put the chapter's secrets into the store

**Why:** A secret that exists only in a file on one computer is lost when that person or that computer is.

**Who:** The central support organization

**Finish first:**

- step 8.7 List the secrets by name
- step 2.7 Set up the chapter's password vault

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the chapter's Operations vault in Proton Pass.
2. For each name on the list from step 8.7 whose step has already happened, check there is an entry titled with exactly that name, for example ESPO_API_KEY. The machine secrets are created later, in stages 9 to 11, and go straight into the vault under the same titles as each is made.
   *You should see:* An entry for every secret that exists so far, titled with its name from the list.
3. Ask a second named person to open each entry in their own Proton Pass.
   *You should see:* The second person can open every entry.

**Done when all of these are true:**

- Every secret a person holds is in the chapter's Proton Pass Operations vault (step 2.7). That is all seven except the database connection, which the hosting platform holds (step 11.4).
- At least two named people can reach each one.
- None of them exists only in a file on one person's computer.

**How to check:** A second named person opens each secret without help.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Treating a file on one laptop as good enough. Regenerating the deployment settings from the hosting provider scrambles the passwords inside them. Cleveland has lost working passwords that way.

---

## 8.9 Review the completed form

**Why:** A wrong value becomes a fault in every later stage, and a second reader catches what the first misses.

**Who:** The chapter and the central support organization — the chapter's setup contact and someone from the central support organization

**Finish first:**

- step 8.2 Fill in the chapter's name and identity
- step 8.3 Fill in the web addresses
- step 8.4 Fill in the Google details
- step 8.5 Fill in the CRM details
- step 8.6 Decide every feature switch
- step 8.7 List the secrets by name

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Meet, in person or on a call, with the page open on both screens.
2. Read every question and its answer aloud, section by section.
   *You should see:* The line at the top of the page reading that every question is answered, apart from the shared drive identifier.
3. The central support organization: run the curl check from step 8.3 on every address again:
   - curl -sI ADDRESS
   *You should see:* A first line of HTTP/2 200 for every address except the applications' address and the CRM address, which do not exist yet.
4. At the bottom of the page, in the section Sign-off, each of the two people types their own name and clicks Sign off.
   *You should see:* Both names listed with the date.

**Done when:** Two people have read the whole form together in one sitting and both have signed it off.

**How to check:** Both names and the date are in the page's Sign-off section.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 8.10 Store the form where the central support organization can reach it

**Why:** Stages 9 to 12 are built from the form, so the people building them have to be able to open it.

**Who:** The central support organization

**Finish first:**

- step 8.9 Review the completed form

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. In a Claude Code session in the folder ~/Dropbox/Projects/cbm-client-intake, type this request, with the page's link in place of PAGE-LINK:
   - Write the chapter values file from the chapter information page PAGE-LINK with scripts/chapter_form/to_values.py.
   *You should see:* A message naming the file written, prds/chapter-network/chapters/CHAPTER-SLUG-values.yaml, and reading that the check passed. If the check names a question, the answer on the page is wrong or missing: correct it on the page and ask again.
2. Open the file and check it holds no secret value. Every line under secrets must be a name only.
3. Commit it with the message "docs(chapter-network): CHAPTER-SLUG chapter information form", and push it.
4. Ask a second person at the central support organization to open the file from the remote repository.
   *You should see:* The file opens, with both reviewers' names at the top.

**Done when:** The form is in the agreed place and the central support organization has confirmed it can open it.

**How to check:** A second person at the central support organization opens it.

**If it didn't work:** If an answer changes after the file is written, change it on the page and write the file again. The page is the record; the file is always produced from it.

**What usually goes wrong:** Editing the file by hand. The page and the file then disagree, and the next time the file is written the hand edit is lost.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.6 | 09-23-26 12:20 | Step 8.6's page button renamed Use recommended answers, and the step now says exactly what it does (Doug, 09-23-26). |
| 0.5 | 09-23-26 12:10 | Step 8.1 shares the page by link instead of by email invitation. A published page starts private and shows a signed-out visitor a sign-in page; opened to anyone with the link, the Boston chapter's page worked with no claude.ai account (Doug, 09-23-26). |
| 0.4 | 09-23-26 11:45 | The form becomes a web page, built from this stage's data (Doug, 09-23-26). Each question now carries what it means, where to find the answer and what goes wrong if it is wrong, in a new fields list the guide and the page both read. Step 8.1 publishes the page and invites the setup contact; step 8.9 signs off on the page; step 8.10 writes the values file from the page's answers instead of by hand. New questions: the Google administrator the software acts as (it was on no step), and whether the chapter runs Zoom webinars and creates mentors' mailboxes automatically. The switches' starting values changed: the Google features and deploy_on_push are on, because the worker reads its mail switches only at start-up. |
| 0.3 | 09-19-26 14:45 | Steps 8.7 and 8.8: the database connection is held by the hosting platform and never goes in the vault, matching step 11.3 (Doug, 09-19-26). |
| 0.2 | 09-19-26 00:05 | Every action made precise (Doug, 09-19-26): each section of the form filled key by key with what goes in it and an example, the sixteen switches with their starting values, the secret names with the step that creates each, vault entry titles, curl checks for every address, and the exact file path the finished form is saved at. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for filling in the chapter information form (5-Methods-Form-Accounts-Checks.md, version 0.4) with the step list's finishing tests. Each form field is now produced by a named step. |
