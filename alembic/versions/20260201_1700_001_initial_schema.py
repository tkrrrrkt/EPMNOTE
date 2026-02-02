"""Initial schema - Articles and Snippets

Revision ID: 001
Revises:
Create Date: 2026-02-01 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ArticleStatus enum using raw SQL for clean idempotency
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE articlestatus AS ENUM (
                'PLANNING', 'RESEARCHING', 'WAITING_INPUT',
                'DRAFTING', 'REVIEW', 'COMPLETED'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create SnippetCategory enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE snippetcategory AS ENUM (
                'FAILURE', 'OPINION', 'TECH', 'HOOK'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create articles table
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("week_id", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("target_persona", sa.String(255), nullable=True),
        sa.Column("seo_keywords", sa.String(255), nullable=True),
        sa.Column("competitor_analysis", postgresql.JSONB, nullable=True),
        sa.Column("research_summary", sa.Text, nullable=True),
        sa.Column("outline_json", postgresql.JSONB, nullable=True),
        sa.Column("hook_statement", sa.Text, nullable=True),
        sa.Column("content_outline", sa.Text, nullable=True),
        sa.Column("draft_content_md", sa.Text, nullable=True),
        sa.Column("final_content_md", sa.Text, nullable=True),
        sa.Column("title_candidates", postgresql.JSONB, nullable=True),
        sa.Column("image_prompts", postgresql.JSONB, nullable=True),
        sa.Column("sns_posts", postgresql.JSONB, nullable=True),
        sa.Column("review_score", sa.Integer, nullable=True),
        sa.Column("review_feedback", sa.Text, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PLANNING", "RESEARCHING", "WAITING_INPUT",
                "DRAFTING", "REVIEW", "COMPLETED",
                name="articlestatus", create_type=False
            ),
            nullable=False,
            server_default="PLANNING",
            index=True,
        ),
        sa.Column("is_uploaded", sa.Boolean, server_default="false"),
        sa.Column("published_url", sa.String(500), nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create snippets table
    op.create_table(
        "snippets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "category",
            postgresql.ENUM(
                "FAILURE", "OPINION", "TECH", "HOOK",
                name="snippetcategory", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("attachment_path", sa.String(500), nullable=True),
        sa.Column("attachment_type", sa.String(50), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("snippets")
    op.drop_table("articles")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS snippetcategory")
    op.execute("DROP TYPE IF EXISTS articlestatus")
