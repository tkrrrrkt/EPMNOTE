"""
EPM Note Engine - Database Connection Management

Provides synchronous and asynchronous database session management.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.database.models import Base


def get_engine():
    """
    Get SQLAlchemy engine for synchronous operations.

    Returns:
        SQLAlchemy Engine instance.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.log_level == "DEBUG",
        pool_pre_ping=True,
    )


def get_session_factory():
    """
    Get session factory for creating database sessions.

    Returns:
        sessionmaker instance.
    """
    engine = get_engine()
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Automatically handles commit/rollback and session cleanup.

    Yields:
        SQLAlchemy Session instance.

    Example:
        with get_session() as session:
            articles = session.query(Article).all()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Initialize database tables.

    Creates all tables defined in the models if they don't exist.
    For production, use Alembic migrations instead.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """
    Drop all database tables.

    WARNING: This will delete all data. Use only for testing/development.
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


# ===========================================
# Async Support (for future use)
# ===========================================

def get_async_engine():
    """
    Get SQLAlchemy async engine.

    Note: Requires asyncpg to be installed.

    Returns:
        SQLAlchemy AsyncEngine instance.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = get_settings()
    return create_async_engine(
        settings.async_database_url,
        echo=settings.log_level == "DEBUG",
        pool_pre_ping=True,
    )


def get_async_session():
    """
    Get async session factory.

    Returns:
        async_sessionmaker instance.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = get_async_engine()
    return async_sessionmaker(bind=engine, autocommit=False, autoflush=False)
