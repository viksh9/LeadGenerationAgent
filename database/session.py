"""Engine creation, schema init, and session lifecycle for SQLite/SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from database.models import Base


def get_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    database_url = url or settings.database_url
    if database_url.startswith("sqlite"):
        # SQLite: no server-side pool; keep the cross-thread flag. pool_pre_ping is
        # cheap and harmless (guards against stale connections after a restart).
        return create_engine(
            database_url, connect_args={"check_same_thread": False},
            future=True, pool_pre_ping=True,
        )
    # Server databases (e.g. Postgres): a real connection pool with pre-ping so a
    # dropped DB connection is detected and replaced rather than erroring (§15).
    return create_engine(
        database_url, future=True, pool_pre_ping=True,
        pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout, pool_recycle=settings.db_pool_recycle,
    )


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    engine = engine or get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


# Additive columns introduced after a table first shipped. SQLite's create_all
# does NOT alter existing tables, so we add any missing ones idempotently on init.
# ADD COLUMN is non-destructive; only additive, nullable/defaulted columns belong here.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "leads": {
        "location_all": "VARCHAR(1024)",   # full hiring-city list for the Excel export
    },
    "decision_makers": {
        # ContactOut POC enrichment (Prompt 44) — additive, all nullable/defaulted.
        "company_domain": "VARCHAR(255)",
        "match_score": "INTEGER DEFAULT 0",
        "contact_trust_score": "INTEGER DEFAULT 0",
        "contact_trust_status": "VARCHAR(24)",
        "is_current": "BOOLEAN DEFAULT 1",
    },
    "companies": {
        # Public-intelligence identity (Prompt 45) — additive.
        "linkedin_url": "VARCHAR(512)",
        "wikidata_id": "VARCHAR(32)",
        # Official company intelligence (Prompt 46) — additive.
        "contact_url": "VARCHAR(1024)",
        "careers_url": "VARCHAR(1024)",
        "leadership_url": "VARCHAR(1024)",
        "company_phone": "VARCHAR(64)",
        "company_email": "VARCHAR(320)",
        "full_address": "VARCHAR(512)",
        "postal_code": "VARCHAR(32)",
        "data_trust_score": "INTEGER DEFAULT 0",
        "official_verified_at": "DATETIME",
        # OpenCorporates legal verification (Prompt 47) — additive.
        "company_number": "VARCHAR(64)",
        "jurisdiction_code": "VARCHAR(16)",
        "company_status": "VARCHAR(24)",
        "incorporation_date": "VARCHAR(24)",
        "registry_url": "VARCHAR(1024)",
        "opencorporates_url": "VARCHAR(1024)",
        "opencorporates_id": "VARCHAR(128)",
        "registered_address": "VARCHAR(512)",
        "india_entity_type": "VARCHAR(24)",
    },
    "source_health": {
        "requests_used": "INTEGER DEFAULT 0",
        "request_budget": "INTEGER",
    },
    "business_signals": {
        "company_id": "INTEGER",
        "commercial_intent": "VARCHAR(16) DEFAULT 'UNKNOWN'",
    },
}


def _reconcile_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all already made it with all columns
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


# Performance indexes on hot query columns not covered by model index=True (§16).
# Applied idempotently (CREATE INDEX IF NOT EXISTS) so existing production and
# fresh test databases both get them. Curated — no redundant/duplicate indexes.
_ADDITIVE_INDEXES: list[tuple[str, str, str]] = [
    # (index_name, table, "col" or "col_a, col_b")
    ("ix_leads_updated_at", "leads", "updated_at"),            # list_leads ORDER BY updated_at
    ("ix_leads_created_at", "leads", "created_at"),            # query_leads sort by created_at
    ("ix_leads_prov_score", "leads", "data_provenance, lead_score"),  # common filter+sort
    ("ix_job_records_first_seen_at", "job_records", "first_seen_at"),  # trend/change ranges
    ("ix_job_records_last_seen_at", "job_records", "last_seen_at"),
    ("ix_crm_activities_lead_occurred", "crm_activities", "lead_id, occurred_at"),  # timeline
    ("ix_audit_logs_entity", "audit_logs", "entity_type, entity_id"),  # audit lookups
]


def _reconcile_indexes(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for index_name, table, columns in _ADDITIVE_INDEXES:
            if table not in existing_tables:
                continue
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})'))


def init_db(engine: Engine | None = None) -> None:
    """Create tables if they do not already exist, then reconcile additive columns."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    _reconcile_columns(engine)
    _reconcile_indexes(engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """Commit on success, rollback on error, always close the session."""
    factory = session_factory or create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
