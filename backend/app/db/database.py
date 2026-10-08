from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)


@event.listens_for(engine, "connect")
def _disable_server_side_prepares(dbapi_connection, connection_record):
    """psycopg3 names server-side prepared statements per client connection
    (e.g. _pg3_0). Behind a transaction-mode pooler the same server
    connection is shared across sessions, so a repeated name collides with
    DuplicatePreparedStatement and the whole transaction is lost. Disabling
    preparation is the documented remedy and is harmless for direct
    connections (it only skips a minor optimization)."""
    try:
        dbapi_connection.prepare_threshold = None
    except AttributeError:
        pass

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
