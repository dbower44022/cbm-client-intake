"""Communications — Gmail conversation integration.

Ingests each manager's @cbmentors.org mail for the records they own, cleans it
(core.email_clean), stores it as CConversation/CCommunication records in the
CRM, optionally summarizes with Claude, and backs the session tools'
Communications tab (read + curation + send).

Spec: prds/communications-gmail-integration.md. Everything is a no-op unless
``GMAIL_SYNC`` is enabled.
"""
