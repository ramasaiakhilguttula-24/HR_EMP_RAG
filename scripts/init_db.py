"""Create all PostgreSQL tables from SQLAlchemy models. Usage: python scripts/init_db.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.database import Base, engine
import backend.app.models.document  # noqa: F401 (register tables)
import backend.app.models.query_log  # noqa: F401
import backend.app.models.user  # noqa: F401


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"Tables created: {sorted(Base.metadata.tables.keys())}")


if __name__ == "__main__":
    asyncio.run(main())
