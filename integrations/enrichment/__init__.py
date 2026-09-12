"""Multi-provider contact enrichment (Prompt 49).

Paid providers (Lusha, Apollo, Hunter, Prospeo) behind a normalized interface, used in
a credit-aware waterfall on top of the existing free/public + ContactOut enrichment.
Real data only: nothing is fabricated on failure; provider keys are read from the
environment and never exposed. Exact provider API contracts are documented public
contracts and should be re-verified against each provider's live docs (REQUIRES_REVIEW).
"""
