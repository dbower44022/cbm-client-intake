# Governance, non-payment and exit

Not a phase — this is the organizational half, and it is load-bearing rather than
paperwork. Ruling 6 (the services org holds the only EspoCRM admin accounts) is
what makes ruling 4 (strictly identical function) enforceable rather than
requested, and together they move every configuration change onto the services
org's desk. **That is the trade: sameness is bought with responsiveness.** If the
change-request route is slow, chapters will route around it — not by hacking, but
by asking for their own admin, and the first exception granted ends the
architecture.

---

## Change governance

Ruling 6 routes every configuration change through the services org, so the route
must be visibly responsive.

- **One intake** for change requests, visible to all members — a member should be
  able to see what others have asked for and where it stands.
- **A decision forum** among the funding members, with a published cadence
  matching the release train, and a standing rule that the answer is *core for
  everyone* or *no*. Under ruling 4 there is no third answer, and pretending
  otherwise is how exceptions start.
- **A published turnaround** for the operational requests that are not
  configuration at all — a user added, a permission team changed, a password
  reset. Most requests will be these, and they must never queue behind a design
  decision. Much of this is already self-service in the apps (Mentor
  Administration provisions users through the `ESPO_PROVISION_*` account
  precisely because user creation is admin-only), which is what keeps ruling 6
  from becoming a bottleneck.


---

## Non-payment and exit

Withholding **service** is legitimate. Withholding **access** must be impossible
by construction — these are independent 501(c)(3)s with their own donors, clients
and retention obligations, and a co-op that can switch a member off would never be
granted the admin concession ruling 6 depends on.

- **A frozen chapter keeps running.** Decay is gradual over months: missed Espo
  security releases, Google and Zoom API deprecations, unrotated credentials, and
  eventually a CRM change the frozen app does not know about.
- **"You keep your CRM" is not "you keep your data."** Ruling 2 makes the CRM half
  clean, but material data lives only in the app's Postgres and was deliberately
  never written to the CRM: `record_comment` (the partner and funder Discussion
  streams), the durable submission store with its Gmail thread anchors and the
  whole response-status history, authored analytics metrics and pages, and
  `app_setting` overrides. **The exit kit must include a Postgres export.**
- **Branch B is the hard exit.** A bring-your-own chapter owns its domain and
  walks away intact. A chapter provisioned inside the network Workspace has mail,
  Drive documents (in a shared drive the services org owns, with the service
  account as operational member) and calendars in someone else's tenant.
  Recoverable by Workspace data transfer — but chapters must be told this before
  choosing the branch.
- **Written in:** notice period, defined wind-down, exit kit (CRM dump, Postgres
  export, Drive transfer, per-chapter asset bundle), and a perpetual licence to
  the last version received.
- **Rehearsed once**, on crm-test, like a restore drill, with an owner and a date.
  An unexecuted exit path is a promise, not a capability.
