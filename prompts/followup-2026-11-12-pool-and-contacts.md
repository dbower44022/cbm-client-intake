# Kickoff — follow-up on v0.318.1–v0.318.4

Last Updated: 11-11-26 23:25 · Revision 1.0

Operating mode: DETAIL.

Paste this into a fresh Claude Code session in `~/Dropbox/Projects/cbm-client-intake`.

---

Continue the follow-up on releases v0.318.1 to v0.318.4. All four are live on crm-test and production since 11-11-26 23:17. Read `OPEN-ITEMS.md` items 78 and 79 first, then `CHANGELOG.md` for 0.318.1 to 0.318.4.

Three things are owed, in this order. Stop after each and report to Doug.

1. **Item 78, the last crm-test look.** On crm-test, open the Quarry Street Coffee engagement (`/mentorsessions/record/6a87e78bb055afe56`), go to the Details tab and click **Add Co-Mentors**. Confirm the co-mentor picker opens with no one-item menu under the button. v0.318.3 fixed that menu but nobody has seen the fix rendered. Doug's crm-test login has no mentor profile, so open the record by its address; the nightly reset may change the id, so look it up through `/assignments/api/engagements` if it 404s. If it passes, move item 78 to Resolved.
2. **Item 79, the soak.** Read the crm-test and production web and `delivery-worker` run logs (`doctl apps logs <app-id> <component> --type run`) for database errors since the deploy: *connection slots*, `asyncpg`, `sqlalchemy`, *attached to a different loop*, *pool*, `TimeoutError`. A clean day is the pass. App ids are in the root `CLAUDE.md` Deployment table.
3. **Item 79, the connection count.** Ask Doug to read production's database connections in the DigitalOcean control panel: Databases, the cluster `app-a685a62d…`, Insights, Connections. Ask for the count at rest, and at the next production deploy. The limit for the application is 22. Fewer than about 12 at rest closes item 79.

Context: v0.318.4 made every data store borrow one database pool per process and event loop (`core/store.shared_engine`). A store's `dispose` no longer closes anything; `dispose_shared_engines` does, from the lifespan, the worker's exit and the boot settings read. Measured locally: 4 connections before, 2 after. After a restart the worker's first pass takes about six minutes, so its heartbeat reads stale meanwhile, and one stale-worker alert then is expected.

Never `git stash` in this working copy to test old code: parallel sessions share it. Use `git worktree add` in the scratchpad instead.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-11-26 23:25 | Claude (Claude Code) | Created at the close of the 11-11-26 session. |
