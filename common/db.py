"""Shared SQLite helpers: engine creation + transactional session scope.

Each app defines its own ORM models (its own Declarative Base) and passes that
Base's metadata to init_engine. This keeps the storage adapter generic while
schemas stay app-specific.
"""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def init_engine(path: str, metadata):
    """Create a SQLite engine and ensure all tables in `metadata` exist."""
    engine = create_engine(f"sqlite:///{path}", future=True)
    metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine):
    """Commit on success, roll back on error, always close."""
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
