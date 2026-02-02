"""
EPM Note Engine - Snippet Repository

CRUD operations for Snippet (essence) entities.
"""

from typing import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Snippet, SnippetCategory


class SnippetRepository:
    """Repository for Snippet entity operations."""

    def __init__(self, session: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session instance.
        """
        self.session = session

    def get_all(self) -> Sequence[Snippet]:
        """
        Get all snippets ordered by creation date.

        Returns:
            List of all snippets.
        """
        stmt = select(Snippet).order_by(Snippet.created_at.desc())
        return self.session.scalars(stmt).all()

    def get_by_id(self, snippet_id: str) -> Snippet | None:
        """
        Get snippet by ID.

        Args:
            snippet_id: UUID string of the snippet.

        Returns:
            Snippet instance or None if not found.
        """
        return self.session.get(Snippet, snippet_id)

    def get_by_article_id(self, article_id: str) -> Sequence[Snippet]:
        """
        Get all snippets for a specific article.

        Args:
            article_id: UUID string of the article.

        Returns:
            List of snippets associated with the article.
        """
        stmt = (
            select(Snippet)
            .where(Snippet.article_id == article_id)
            .order_by(Snippet.created_at)
        )
        return self.session.scalars(stmt).all()

    def get_by_category(self, category: SnippetCategory) -> Sequence[Snippet]:
        """
        Get snippets filtered by category.

        Args:
            category: SnippetCategory to filter by.

        Returns:
            List of snippets with the specified category.
        """
        stmt = (
            select(Snippet)
            .where(Snippet.category == category)
            .order_by(Snippet.created_at.desc())
        )
        return self.session.scalars(stmt).all()

    def get_by_tag(self, tag: str) -> Sequence[Snippet]:
        """
        Get snippets containing a specific tag.

        Args:
            tag: Tag string to search for.

        Returns:
            List of snippets containing the tag.
        """
        stmt = (
            select(Snippet)
            .where(Snippet.tags.contains([tag]))
            .order_by(Snippet.created_at.desc())
        )
        return self.session.scalars(stmt).all()

    def create(self, snippet: Snippet) -> Snippet:
        """
        Create a new snippet.

        Args:
            snippet: Snippet instance to create.

        Returns:
            Created snippet with generated ID.
        """
        if not snippet.id:
            snippet.id = str(uuid4())
        self.session.add(snippet)
        self.session.flush()
        return snippet

    def update(self, snippet: Snippet) -> Snippet:
        """
        Update an existing snippet.

        Args:
            snippet: Snippet instance with updated values.

        Returns:
            Updated snippet.
        """
        self.session.merge(snippet)
        self.session.flush()
        return snippet

    def delete(self, snippet_id: str) -> bool:
        """
        Delete a snippet by ID.

        Args:
            snippet_id: UUID string of the snippet.

        Returns:
            True if deleted, False if not found.
        """
        snippet = self.get_by_id(snippet_id)
        if snippet:
            self.session.delete(snippet)
            self.session.flush()
            return True
        return False

    def add_tag(self, snippet_id: str, tag: str) -> Snippet | None:
        """
        Add a tag to a snippet.

        Args:
            snippet_id: UUID string of the snippet.
            tag: Tag string to add.

        Returns:
            Updated snippet or None if not found.
        """
        snippet = self.get_by_id(snippet_id)
        if snippet:
            if snippet.tags is None:
                snippet.tags = []
            if tag not in snippet.tags:
                snippet.tags = snippet.tags + [tag]
                self.session.flush()
            return snippet
        return None

    def remove_tag(self, snippet_id: str, tag: str) -> Snippet | None:
        """
        Remove a tag from a snippet.

        Args:
            snippet_id: UUID string of the snippet.
            tag: Tag string to remove.

        Returns:
            Updated snippet or None if not found.
        """
        snippet = self.get_by_id(snippet_id)
        if snippet and snippet.tags and tag in snippet.tags:
            snippet.tags = [t for t in snippet.tags if t != tag]
            self.session.flush()
            return snippet
        return None

    def bulk_create(self, snippets: list[Snippet]) -> list[Snippet]:
        """
        Create multiple snippets at once.

        Args:
            snippets: List of Snippet instances to create.

        Returns:
            List of created snippets with generated IDs.
        """
        for snippet in snippets:
            if not snippet.id:
                snippet.id = str(uuid4())
        self.session.add_all(snippets)
        self.session.flush()
        return snippets

    def count_by_article(self, article_id: str) -> int:
        """
        Get count of snippets for a specific article.

        Args:
            article_id: UUID string of the article.

        Returns:
            Number of snippets.
        """
        from sqlalchemy import func

        stmt = (
            select(func.count(Snippet.id))
            .where(Snippet.article_id == article_id)
        )
        return self.session.scalar(stmt) or 0
