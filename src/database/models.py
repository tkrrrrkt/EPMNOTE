"""
EPM Note Engine - SQLAlchemy Models

Defines Article and Snippet models with full type safety.
"""

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
    }


class ArticleStatus(str, enum.Enum):
    """Article workflow status."""

    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    WAITING_INPUT = "WAITING_INPUT"
    DRAFTING = "DRAFTING"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"


class SnippetCategory(str, enum.Enum):
    """Snippet (essence) category types."""

    FAILURE = "FAILURE"  # 失敗談
    OPINION = "OPINION"  # 意見・主張
    TECH = "TECH"  # 技術知見
    HOOK = "HOOK"  # フック・導入


class Article(Base):
    """
    Article model representing a Note.com article.

    Tracks the full lifecycle from planning to publication.
    """

    __tablename__ = "articles"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Basic info
    week_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target_persona: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # SEO & Research
    seo_keywords: Mapped[str | None] = mapped_column(String(255), nullable=True)
    competitor_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content structure
    outline_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    hook_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_outline: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Draft content
    draft_content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_content_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated assets
    title_candidates: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Array of strings stored as JSON
    image_prompts: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Array of strings stored as JSON
    sns_posts: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # {"x": "...", "linkedin": "..."}

    # Image suggestions from Unsplash/Pexels API
    image_suggestions: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # [{"query": "...", "images": [...], "source": "unsplash/pexels"}]

    # SEO keyword analysis results
    keyword_analysis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # {"primary_keyword": {...}, "density_score": 85, "suggestions": [...]}

    # SEO Enhancement (v1.2)
    meta_description: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )  # SEO meta description (120-160 chars)
    structured_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON-LD schema (FAQ, HowTo, etc.)
    estimated_read_time: Mapped[int | None] = mapped_column(
        nullable=True
    )  # Reading time in minutes
    cta_variants: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # {"consultation": "...", "download": "...", "case_study": "..."}

    # Review
    review_score: Mapped[int | None] = mapped_column(nullable=True)
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Publication
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus),
        nullable=False,
        default=ArticleStatus.PLANNING,
        index=True,
    )
    is_uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    published_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Metrics
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # {"pv": 0, "likes": 0, "ctr": 0}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    snippets: Mapped[list["Snippet"]] = relationship(
        "Snippet",
        back_populates="article",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, week_id={self.week_id}, title={self.title[:30]}...)>"


class Snippet(Base):
    """
    Snippet model representing user-provided essence/content.

    Stores user inputs like failure stories, opinions, technical insights, and hooks.
    """

    __tablename__ = "snippets"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key
    article_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    category: Mapped[SnippetCategory] = mapped_column(
        Enum(SnippetCategory),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Attachments (MVP対象外 but schema ready)
    attachment_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # MIME type

    # Tags
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    article: Mapped["Article"] = relationship("Article", back_populates="snippets")

    def __repr__(self) -> str:
        return f"<Snippet(id={self.id}, category={self.category}, content={self.content[:30]}...)>"
