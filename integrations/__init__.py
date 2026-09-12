"""Third-party API integrations (real data only).

Each integration lives in its own subpackage with a typed client, response models,
a mapper to the application's domain, and its own exception hierarchy. Credentials
are read from configuration only and are never exposed in responses, logs, the
database, exports, or audit payloads.
"""
