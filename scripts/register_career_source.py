"""Register a verified ATS career source (Greenhouse board / Lever site).

Usage:
    python scripts/register_career_source.py greenhouse <board_token> "<Company Name>"

Only registers a board that was actually VERIFIED against the live ATS API by the
caller (this script does not fabricate boards). Idempotent upsert on
(provider, board_identifier). Marks the source CONNECTED + enabled so scheduled/collector
runs will pull real jobs from it. Persists no jobs itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.career_source_registry import register_career_source
from config import get_settings
from database.models import AtsProvider, CareerSourceStatus
from database.session import create_session_factory, get_engine, init_db

_PROVIDERS = {"greenhouse": AtsProvider.GREENHOUSE, "lever": AtsProvider.LEVER}
_CAREERS_URL = {
    "greenhouse": "https://boards.greenhouse.io/{board}",
    "lever": "https://jobs.lever.co/{board}",
}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: register_career_source.py <greenhouse|lever> <board> \"<Company>\"")
        return 2
    provider_key, board = argv[1].lower(), argv[2]
    company = argv[3] if len(argv) > 3 else None
    if provider_key not in _PROVIDERS:
        print(f"unknown provider '{provider_key}'"); return 2

    engine = get_engine(get_settings().database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        row = register_career_source(
            session, ats_provider=_PROVIDERS[provider_key], board_identifier=board,
            status=CareerSourceStatus.CONNECTED, company_name=company,
            careers_url=_CAREERS_URL[provider_key].format(board=board),
            discovery_method="manual_verified")
        session.commit()
        print(f"registered {provider_key} board '{board}' (id={row.id}, status={row.status.value}, "
              f"enabled={row.enabled}, company={row.company_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
