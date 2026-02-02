"""
EPM Note Engine - Database Module

Provides database connection, session management, and model exports.
"""

from src.database.models import Article, ArticleStatus, Snippet, SnippetCategory, Base
from src.database.connection import (
    get_engine,
    get_session,
    get_async_engine,
    get_async_session,
    init_db,
)

__all__ = [
    # Models
    "Article",
    "ArticleStatus",
    "Snippet",
    "SnippetCategory",
    "Base",
    # Connection
    "get_engine",
    "get_session",
    "get_async_engine",
    "get_async_session",
    "init_db",
]
