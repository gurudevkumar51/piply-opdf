import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

SQLALCHEMY_DATABASE_URL = "sqlite:///./piply_opdf.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 15}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

#: Columns added after a table first shipped. ``create_all`` creates missing
#: *tables* and silently ignores missing *columns*, so an existing database
#: keeps its old shape and every read of a new field fails at runtime instead
#: of at startup.
#:
#: Additive only, and deliberately so: adding a nullable column cannot lose
#: data, while anything that drops or rewrites one needs a person deciding what
#: the old values meant.
LATER_COLUMNS: dict[str, dict[str, str]] = {
    "components": {"evidence_json": "TEXT", "layout_features_json": "TEXT"},
}


def ensure_columns() -> None:
    """Add any column in :data:`LATER_COLUMNS` the database does not have."""
    inspector = inspect(engine)
    for table, columns in LATER_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, kind in columns.items():
            if name in existing:
                continue
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))
            logger.info("Added column %s.%s", table, name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
