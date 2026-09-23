# New Chapter Deployment Guide

**Generated from** `steps/` — do not edit this page; edit the YAML and re-render.

The guide takes a new chapter from nothing to a running system. Work through the stages in order. Each stage opens with why it exists, who does it, and what must be finished first.

---

1. [Set up the chapter as a legal organization](01-set-up-the-chapter-as-a-legal-organization.md)
   The chapter has to exist in law before it can own accounts, sign an agreement or claim nonprofit discounts.
2. [Sign the agreement with the central support organization](02-sign-the-agreement-with-the-central-support-organization.md)
   Everything after this stage involves one organization spending money and holding administrative access inside another organization's accounts.
3. [Register the chapter's domain names](03-register-the-chapter-s-domain-names.md)
   Every address the chapter uses hangs off its domain names: its email, its website, its CRM and its applications.
4. [Set up Google Workspace and the chapter's email](04-set-up-google-workspace-and-the-chapter-s-email.md)
   Google Workspace is Google's paid service for an organization's email, calendars and documents.
5. [Open the hosting and video meeting accounts](05-open-the-hosting-and-video-meeting-accounts.md)
   The chapter's CRM server, its applications and their database all run in a hosting account, and the public webinar programme runs through a video meeting account.
6. [Build the chapter's public website](06-build-the-chapter-s-public-website.md)
   The public website is the chapter's own marketing site.
7. [Write and publish the policy documents](07-write-and-publish-the-policy-documents.md)
   Every public form carries one required consent box that links to four documents.
8. [Fill in the chapter information form](08-fill-in-the-chapter-information-form.md)
   The chapter information form holds the roughly forty answers that differ from one chapter to the next: its name, its addresses, its Google details and its feature switches.
9. [Build the CRM system](09-build-the-crm-system.md)
   The CRM is the chapter's system of record: every client, mentor, partner, funder and meeting lives in it, and every application reads and writes it.
10. [Set up the Google permissions the software needs](10-set-up-the-google-permissions-the-software-needs.md)
   The applications read and send the chapter's email, keep calendars in step, file documents on the shared drive and create mentor mailboxes.
11. [Deploy the chapter's applications](11-deploy-the-chapter-s-applications.md)
   The applications are what the chapter's staff, mentors and the public actually use: the intake forms, the staff tools and the public events page.
12. [Set up backups and monitoring](12-set-up-backups-and-monitoring.md)
   This stage makes sure the chapter's records can be got back after a mistake or a failure, and that a person finds out when the system stops working.
13. [Put the chapter's pages on its website](13-put-the-chapter-s-pages-on-its-website.md)
   The public learns about the chapter through its website.
14. [Create the staff accounts](14-create-the-staff-accounts.md)
   Each member of the chapter's staff needs their own account to use the applications, on the team that opens the pages their job needs.
15. [Bring in the chapter's records and create the mentor accounts](15-bring-in-the-chapter-s-records-and-create-the-mentor-accounts.md)
   A chapter arrives with clients, companies, partners, funders and mentors it already knows about.
16. [Train the chapter's staff](16-train-the-chapter-s-staff.md)
   Staff learn the system on invented records before they touch real ones.
17. [Check everything works before going live](17-check-everything-works-before-going-live.md)
   This stage proves the chapter's system works end to end before any real client uses it: each team reaches its own pages and nobody else's, and a public application travels from the website through assignment to a mentor.
18. [Hand over and start normal support](18-hand-over-and-start-normal-support.md)
   This stage moves the chapter from being set up to being supported, and proves the chapter can reach everything it owns without help.

---

## Words in capitals

A word in capitals inside a command stands for a value to type in its place. These are used in more than one stage. One used in a single step is explained in that step.

- **SHORT-LABEL**: The chapter's short label: a short lower-case name, such as boston, built into the names of everything the software creates for the chapter (the application boston-intake, the database boston-db, the Google project boston-apps). People never see it. It is not the chapter's name (Boston Business Mentors) and not its abbreviation (BBM). *Comes from:* Step 8.2, the question Short label.
- **CHAPTER-NAME**: The chapter's full name, exactly as people see it. *Comes from:* Step 8.2, the question Chapter name.
- **WEBSITE-DOMAIN**: The domain name of the chapter's public website, such as lakesidebusinessmentors.org. *Comes from:* Stage 3, recorded on the chapter information form in step 8.3.
- **EMAIL-DOMAIN**: The domain name the chapter's email addresses end in. *Comes from:* Step 4.2.
- **CRM-ADDRESS**: The CRM's web address, without https://. *Comes from:* Step 8.5, the question Web address (URL) the CRM will use.
- **APP-ADDRESS**: The applications' web address. *Comes from:* Step 8.3, the question Web address (URL) the applications will use.
- **ALERT-ADDRESS**: The email address that receives the system's alerts. *Comes from:* Step 8.4, the question Alert receiving address.
- **CHAPTER-VALUES-FILE**: The filled-in chapter information form, saved as prds/chapter-network/chapters/SHORT-LABEL-values.yaml. *Comes from:* Step 8.10.
- **KEY-FILE**: The private SSH key that opens a command line on the CRM server, ~/.ssh/crm-SHORT-LABEL on the build computer. *Comes from:* Step 9.2.
- **SERVER-IP**: The CRM server's internet address. *Comes from:* Step 9.2.
- **CHAPTER-ENV-FILE**: The chapter's settings file on the build computer, ~/.config/cbm-SHORT-LABEL/SHORT-LABEL.env. *Comes from:* Step 9.10.
- **APP-ID**: The chapter application's identifier on the hosting platform. *Comes from:* Step 11.5.
