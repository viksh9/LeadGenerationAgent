"""Provider abstractions for email sending and CRM sync (§9, §18).

Nothing is ever sent or synced unless a provider is explicitly configured via
environment variables. Credentials are read from settings/env only — never
hard-coded, never logged.
"""
