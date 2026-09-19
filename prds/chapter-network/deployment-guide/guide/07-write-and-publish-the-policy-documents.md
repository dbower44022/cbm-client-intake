# Stage 7 — Write and publish the policy documents

**Version:** 0.2  
**Last Updated:** 09-19-26 00:05  
**Generated from** `steps/stage-07.yaml` — do not edit this page; edit the YAML and re-render.

---

## Why this stage

Every public form carries one required consent box that links to four documents. Two are codes: the code of conduct, and the mentor code of ethics. Two are legal: the terms of use, and the privacy policy. The links must lead to this chapter's own documents, because showing one city's applicants another city's privacy policy is a legal problem. The chapter writes the documents with its own legal adviser; this stage covers only what the software needs from them.

**Who:** The chapter, with its own legal adviser. The central support organization supplies the list of what personal information the software collects, and gives no legal advice.  
**Time:** Not known. It depends on the chapter's legal adviser.  
**When this stage is done:** The four addresses go on the chapter information form (stage 8), and from there into the consent box on every public form.

**Before you start:**

- The website, published (step 6.2)
- A named person at the chapter who can edit the website (step 6.4)

**Steps in this stage:**

- 7.1 Write and publish the client code of conduct
- 7.2 Write and publish the mentor code of ethics
- 7.3 Write and publish the terms
- 7.4 Write and publish the privacy policy
- 7.5 Have the four documents reviewed
- 7.6 Record the four web addresses

---

## 7.1 Write and publish the client code of conduct

**Why:** The consent box on the client, partner and funder forms links to it as "Code of Conduct".

**Who:** The chapter

**Finish first:**

- step 6.2 Publish the website
- step 6.4 Confirm someone at the chapter can edit the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Write the document with the chapter's legal adviser. Give it the title "Client Code of Conduct". The client, partner and funder forms link to it from the words Client Code of Conduct or Code of Conduct, depending on the form.
2. Publish it as a public page on the chapter's website at exactly this address, the same path Cleveland uses: https://WEBSITE-DOMAIN/client-code-of-conduct/
3. In a terminal, run exactly:
   - curl -sI https://WEBSITE-DOMAIN/client-code-of-conduct/
   *You should see:* A first line of HTTP/2 200. A 302 to a sign-in page means the page is a draft or private.
4. Open the same address in a private browser window.
   *You should see:* The document, without being asked to sign in.
5. Write the address on the chapter information form under web: policy_client_conduct_url. It becomes the setting POLICY_CLIENT_CONDUCT_URL.

**Done when:** The document is published on the chapter's website and opens without signing in.

**How to check:** The page opens in a private browser window.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A page published as a draft, or behind a sign-in. It opens for the person who wrote it and for nobody else. The private window is what catches this.

---

## 7.2 Write and publish the mentor code of ethics

**Why:** The volunteer application form's "Code of Conduct" link goes to this document, which is different from the client code of conduct.

**Who:** The chapter

**Finish first:**

- step 6.4 Confirm someone at the chapter can edit the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Write the document with the chapter's legal adviser. Give it the title "Mentor Code of Ethics". It is a separate document from the client code of conduct. The volunteer form's link reads Code of Conduct and leads here.
2. Publish it as a public page on the chapter's website at exactly this address, the same path Cleveland uses: https://WEBSITE-DOMAIN/mentor-code-of-ethics/
3. In a terminal, run exactly:
   - curl -sI https://WEBSITE-DOMAIN/mentor-code-of-ethics/
   *You should see:* A first line of HTTP/2 200. A 302 to a sign-in page means the page is a draft or private.
4. Open the same address in a private browser window.
   *You should see:* The document, without being asked to sign in.
5. Write the address on the chapter information form under web: policy_mentor_ethics_url. It becomes the setting POLICY_MENTOR_ETHICS_URL.

**Done when:** The document is published and opens without signing in.

**How to check:** The page opens in a private browser window.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Publishing one code for both. The software links two different addresses, and a mentor applicant would then agree to the client code of conduct.

---

## 7.3 Write and publish the terms

**Why:** The consent box on every public form links to it as "Terms of Use".

**Who:** The chapter

**Finish first:**

- step 6.4 Confirm someone at the chapter can edit the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Write the document with the chapter's legal adviser. Give it the title "Terms of Use". Every public form's link reads Terms of Use.
2. Publish it as a public page on the chapter's website at exactly this address, the same path Cleveland uses: https://WEBSITE-DOMAIN/legal-notices/
3. In a terminal, run exactly:
   - curl -sI https://WEBSITE-DOMAIN/legal-notices/
   *You should see:* A first line of HTTP/2 200. A 302 to a sign-in page means the page is a draft or private.
4. Open the same address in a private browser window.
   *You should see:* The document, without being asked to sign in.
5. Write the address on the chapter information form under web: policy_terms_url. It becomes the setting POLICY_TERMS_URL.

**Done when:** The document is published and opens without signing in.

**How to check:** The page opens in a private browser window.

**If it didn't work:** Stop, and ask the central support organization before going on.

---

## 7.4 Write and publish the privacy policy

**Why:** The consent box on every public form links to it, and it must describe what this chapter's system collects, under this chapter's name.

**Who:** The chapter and the central support organization — the chapter writes it, the central support organization says what the software collects

**Finish first:**

- step 6.4 Confirm someone at the chapter can edit the website

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. The central support organization gives the chapter's adviser a plain list of what personal information the software collects and where it is kept. There is no finished list yet (work list item 13). Until there is, give this outline:
   - Names, contact details and business details from the public forms, kept in the chapter's CRM.
   - Every form submission, also held in the application's own database.
   - Email between mentors and clients, copied onto the client's record in the CRM.
   - Documents, kept in the chapter's Google shared drive.
2. The chapter writes the policy with its legal adviser. Give it the title "Privacy Policy". Every public form's link reads Privacy Policy.
3. Publish it as a public page at exactly this address, the same path Cleveland uses: https://WEBSITE-DOMAIN/privacy-policy/
4. In a terminal, run exactly:
   - curl -s https://WEBSITE-DOMAIN/privacy-policy/ | grep -c -i cleveland
   *You should see:* The number 0. Any other number means Cleveland's name is still in the page.
5. Open the same address in a private browser window and read which organization the policy names.
   *You should see:* The document, without a sign-in, naming this chapter.
6. Write the address on the chapter information form under web: policy_privacy_url. It becomes the setting POLICY_PRIVACY_URL.

**Done when all of these are true:**

- The document is published.
- The document opens without signing in.
- The document names this chapter rather than any other organization.

**How to check:** The page opens in a private browser window, and the organization it names is this chapter.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Starting from another chapter's policy and missing a name. The finishing test for this step exists for that reason.

---

## 7.5 Have the four documents reviewed

**Why:** The documents are live the moment they are published, and the consent box points at them as soon as the applications are deployed.

**Who:** The chapter

**Finish first:**

- step 7.1 Write and publish the client code of conduct
- step 7.2 Write and publish the mentor code of ethics
- step 7.3 Write and publish the terms
- step 7.4 Write and publish the privacy policy

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Send the chapter's legal adviser the four addresses from steps 7.1 to 7.4.
2. The adviser reads all four and replies in writing that they may be published, naming each document.
   *You should see:* A written reply naming all four documents.
3. Save the reply in the chapter's shared drive, in a folder named Legal, with the date in its file name. The central support organization plays no part in this review.

**Done when:** Whoever advises the chapter on legal matters has read all four and confirmed they may be published.

**How to check:** The written confirmation is kept with the chapter's records.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** Publishing first and reviewing later. The documents are live as soon as they are published.

---

## 7.6 Record the four web addresses

**Why:** The software's four policy settings are filled from these addresses, and every one defaults to Cleveland's documents.

**Who:** The chapter checked by the central support organization

**Finish first:**

- step 7.5 Have the four documents reviewed

> This step has not yet been done on a real chapter. Follow it, and tell the central support organization anything that differs.

**Do this:**

1. Open the chapter information form and check the web: section holds exactly these four keys, each with an address copied from the browser's address bar, not typed from memory:
   - policy_client_conduct_url: https://WEBSITE-DOMAIN/client-code-of-conduct/
   - policy_mentor_ethics_url: https://WEBSITE-DOMAIN/mentor-code-of-ethics/
   - policy_terms_url: https://WEBSITE-DOMAIN/legal-notices/
   - policy_privacy_url: https://WEBSITE-DOMAIN/privacy-policy/
2. In a terminal, run this once for each of the four addresses, putting the address in place of POLICY-ADDRESS:
   - curl -sI POLICY-ADDRESS
   *You should see:* A first line of HTTP/2 200 for all four.
3. Check that none of the four addresses contains clevelandbusinessmentors.org. Each setting defaults to Cleveland's document, so a copied Cleveland address would pass every other check.

**Done when:** All four addresses are written on the chapter information form and each one has been opened and checked.

**How to check:** All four open from the form.

**If it didn't work:** Stop, and ask the central support organization before going on.

**What usually goes wrong:** A changed address later. If the chapter moves a document on its website, the consent box links break silently. Moving a policy document needs a change request (step 18.2), so the setting is changed at the same time.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 0.2 | 09-19-26 00:05 | Every action made precise (Doug, 09-19-26): the title each document must carry to match the consent box's link text, the exact address to publish it at (Cleveland's paths), a curl check that it is public, a check that the privacy policy no longer names Cleveland, and the form key and setting each address goes into. |
| 0.1 | 09-18-26 17:20 | First version as data, converted from the methods for the policy documents (9-Methods-Hosting-Website-Policies.md, version 0.4) with the step list's finishing tests. |
