"""
EPM Note Engine - Article Repository

CRUD operations for Article entities with status transition validation.
"""

from typing import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import Article, ArticleStatus


class ArticleRepository:
    """Repository for Article entity operations."""

    # Valid status transitions
    VALID_TRANSITIONS: dict[ArticleStatus, list[ArticleStatus]] = {
        ArticleStatus.PLANNING: [ArticleStatus.RESEARCHING],
        ArticleStatus.RESEARCHING: [ArticleStatus.WAITING_INPUT],
        ArticleStatus.WAITING_INPUT: [ArticleStatus.DRAFTING],
        ArticleStatus.DRAFTING: [ArticleStatus.REVIEW],
        ArticleStatus.REVIEW: [ArticleStatus.DRAFTING, ArticleStatus.COMPLETED],
        ArticleStatus.COMPLETED: [],  # Terminal state
    }

    def __init__(self, session: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session instance.
        """
        self.session = session

    def get_all(self) -> Sequence[Article]:
        """
        Get all articles ordered by week_id.

        Returns:
            List of all articles.
        """
        stmt = select(Article).order_by(Article.week_id)
        return self.session.scalars(stmt).all()

    def get_by_id(self, article_id: str) -> Article | None:
        """
        Get article by ID.

        Args:
            article_id: UUID string of the article.

        Returns:
            Article instance or None if not found.
        """
        return self.session.get(Article, article_id)

    def get_by_status(self, status: ArticleStatus) -> Sequence[Article]:
        """
        Get articles filtered by status.

        Args:
            status: ArticleStatus to filter by.

        Returns:
            List of articles with the specified status.
        """
        stmt = (
            select(Article)
            .where(Article.status == status)
            .order_by(Article.week_id)
        )
        return self.session.scalars(stmt).all()

    def get_by_week_id(self, week_id: str) -> Article | None:
        """
        Get article by week_id.

        Args:
            week_id: Week identifier (e.g., "Week1-1").

        Returns:
            Article instance or None if not found.
        """
        stmt = select(Article).where(Article.week_id == week_id)
        return self.session.scalars(stmt).first()

    def create(self, article: Article) -> Article:
        """
        Create a new article.

        Args:
            article: Article instance to create.

        Returns:
            Created article with generated ID.
        """
        if not article.id:
            article.id = str(uuid4())
        self.session.add(article)
        self.session.flush()
        return article

    def update(self, article: Article) -> Article:
        """
        Update an existing article.

        Args:
            article: Article instance with updated values.

        Returns:
            Updated article.
        """
        self.session.merge(article)
        self.session.flush()
        return article

    def update_status(
        self,
        article_id: str,
        new_status: ArticleStatus,
        validate_transition: bool = True,
    ) -> Article:
        """
        Update article status with optional transition validation.

        Args:
            article_id: UUID string of the article.
            new_status: New status to set.
            validate_transition: If True, validate the status transition.

        Returns:
            Updated article.

        Raises:
            ValueError: If article not found or invalid transition.
        """
        article = self.get_by_id(article_id)
        if not article:
            raise ValueError(f"Article not found: {article_id}")

        if validate_transition:
            valid_next = self.VALID_TRANSITIONS.get(article.status, [])
            if new_status not in valid_next:
                raise ValueError(
                    f"Invalid status transition: {article.status} -> {new_status}. "
                    f"Valid transitions: {valid_next}"
                )

        article.status = new_status
        self.session.flush()
        return article

    def delete(self, article_id: str) -> bool:
        """
        Delete an article by ID.

        Args:
            article_id: UUID string of the article.

        Returns:
            True if deleted, False if not found.
        """
        article = self.get_by_id(article_id)
        if article:
            self.session.delete(article)
            self.session.flush()
            return True
        return False

    def bulk_create(self, articles: list[Article]) -> list[Article]:
        """
        Create multiple articles at once.

        Args:
            articles: List of Article instances to create.

        Returns:
            List of created articles with generated IDs.
        """
        for article in articles:
            if not article.id:
                article.id = str(uuid4())
        self.session.add_all(articles)
        self.session.flush()
        return articles

    def count_by_status(self) -> dict[ArticleStatus, int]:
        """
        Get count of articles grouped by status.

        Returns:
            Dictionary mapping status to count.
        """
        from sqlalchemy import func

        stmt = (
            select(Article.status, func.count(Article.id))
            .group_by(Article.status)
        )
        results = self.session.execute(stmt).all()
        return {status: count for status, count in results}
