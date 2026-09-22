"""All tables register on Base.metadata (guards Alembic autogenerate misses)."""

from backend.app.core.database import Base
from backend.app.models import document, query_log, user  # noqa: F401


def test_tables_registered():
    names = set(Base.metadata.tables.keys())
    assert {"users", "documents", "query_logs", "security_events"} <= names
