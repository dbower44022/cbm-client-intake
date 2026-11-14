# surveys/ — the survey engine

Last Updated: 11-13-26 14:53 · Revision 1.0

What any kind of survey uses (ruling BE23, `prds/business-evaluation-plan.md`).
Claude Code loads this file only when a session works in this folder.

- **Survey definitions** (`definitions.py`): versioned YAML files,
  `<key>.v<n>.yaml`, one survey per file; the format is in the module's
  docstring. A file someone has answered is never edited: a change is a new
  version file.
- **Answers** (`answers.py`): each value checked by question type, the
  required answers, a survey's state, and the readable question-and-answer
  text and version-stamped JSON.
- **The link store and the saved answers** (`store.py`, tables `survey_link`
  and `survey_answer`, migrations 0044 and 0047). A link is a random token,
  never a CRM id. It names its survey purpose, the CRM record it points at
  (`entity_type`, `record_id`), the purpose's own data (`data`, JSON) and a
  display snapshot (`display_name`), so opening a link never calls the CRM.
  Both tables are training data on the sandbox. In tests the in-memory twin
  is `tests/survey_fakes.MemoryStore`.
- **The submit retry** (`service.run_retry_cycle`): the worker hands a
  refused submit back to its purpose with backoff (1 minute to 6 hours), on
  each purpose's own interval setting.
- **The public page** (`router.py`, `frontend/`): `/survey/{token}`,
  `/api/survey/…`, `/survey-assets/…`. Consent first, save as the person
  goes, submit with honeypot and submission token. While no purpose's switch
  is on, every one of these answers 404 before any database read
  (`core/app.py`'s `_dark_surveys`). A link whose purpose is off, unknown,
  expired or replaced gets one "no longer valid" page. That page's words
  are shared by every purpose, because an unknown link has no purpose. They
  are phase 1's (Doug's option A, 11-13-26).

**This package holds no code specific to any survey purpose and imports
none**; `tests/test_survey_engine.py` fails if it does.

## Adding a survey purpose

1. A package of its own, say `feedback/`, with its definitions in a folder
   of their own (`feedback/surveys/*.yaml`).
2. A module that registers it on import, as `evaluation/purpose.py` does:
   `registry.register(registry.SurveyPurpose(...))`. It declares:
   - `key`: stored on every link; never changed once a link exists.
   - `switch`, `link_days`, `retry_seconds`: the names of three `Settings`
     attributes (add them to `core/config.py` and `core/settings_registry.py`).
   - `definitions_dir`, and `loader` when its files carry top-level keys of
     their own or need checks of their own (`LoaderRules`: `extra_keys`, a
     `Survey` subclass, `check`, `required_keys`).
   - `surveys_for(link)`: the survey keys a link opens, in answer order,
     usually from `link["data"]`.
   - `page`: a `PageText` — the title, the first screen, the consent box,
     the list's text and the all-done text.
   - `submit(ctx)`: hands a submitted survey on; raise one of `retryable` to
     have it retried.
   - `first_save(ctx)`: optional; runs once per survey on its first save that
     holds an answer, best-effort.
   - `client(app)`: the client `submit` writes through.
3. Import that module in `core/app.py` and in `worker.py`, beside
   `evaluation.purpose`.
4. Make links with `SurveyStore.create_link(purpose=…, entity_type=…,
   record_id=…, data=…, display_name=…, …)` and find them again with
   `links_for_record`.
5. Tests: a definitions test that loads every shipped file, and the
   purpose's own submit. The engine's behaviour is already tested.

Not in the engine yet (plan § 8): a general Survey Response record in the
CRM, sending to many people, totals across responses, surveys staff can edit.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-13-26 14:53 | Claude (Claude Code) | Created in phase 2b (ruling BE23). |
