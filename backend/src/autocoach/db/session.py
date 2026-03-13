"""SQLAlchemy engine and session factory helpers."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(db_url: str) -> Engine:
    """Create a SQLAlchemy engine from a connection URL."""
    return create_engine(db_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to the given engine."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Context manager that yields a session, commits on success, rolls back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
