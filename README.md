# cbm-client-intake

Custom web application for the Cleveland Business Mentors **Client Intake** process.

A prospective client completes a dynamic, branching intake form. A completed
submission creates three linked records in the system of record: an Account
(the client organization), a Contact (the applicant, linked to the Account),
and an Engagement (the mentoring request, linked to the Account).

## Documentation

Product Requirements Documents live in [`prds/`](prds/):

- **Requirements Specification** — what the application must do. Derived from,
  and kept aligned by carry-forward with, the Mentoring Domain Client Intake
  process document in the `dbower44022/ClevelandBusinessMentoring` repository.
- **Technical Design** — how the application is built. Derives from the
  Requirements Specification.

The business-level definition of the Client Intake process is **not** owned
here. It lives in the Mentoring Domain Client Intake process document
(MN-INTAKE) in the Cleveland Business Mentoring repository.
