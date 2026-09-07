"""Business-signal collection framework.

Collects IT-business signals (news, project announcements, contracts, tenders,
company newsroom items) from permitted official APIs / feeds only. Reuses the
shared safe HTTP client (SSRF/size/redirect/robots guards) — never scrapes behind
auth/paywalls/CAPTCHA and never executes page JavaScript.
"""
