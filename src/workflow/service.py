"""
EPM Note Engine - Workflow Service

High-level service for executing and managing article generation workflows.
"""

import logging
from typing import Callable

from src.database.connection import get_session
from src.database.models import Article, ArticleStatus
from src.repositories.article_repository import ArticleRepository
from src.repositories.snippet_repository import SnippetRepository
from src.workflow.graph import (
    ArticleState,
    create_initial_state,
    create_workflow_graph,
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """
    Service for managing article generation workflows.

    Provides high-level methods for running workflows and
    synchronizing state with the database.
    """

    def __init__(self) -> None:
        """Initialize the workflow service."""
        self.graph = create_workflow_graph()

    def run_workflow(
        self,
        article_id: str,
        seo_keywords: str,
        on_phase_change: Callable[[str], None] | None = None,
        tavily_profile: str | None = None,
    ) -> ArticleState:
        """
        Run a complete workflow for an article.

        Args:
            article_id: The article ID to process.
            seo_keywords: Target SEO keywords.
            on_phase_change: Optional callback for phase changes.

        Returns:
            Final workflow state.
        """
        logger.info(f"Starting workflow for article: {article_id}")

        with get_session() as session:
            article_repo = ArticleRepository(session)
            snippet_repo = SnippetRepository(session)

            # Load article
            article = article_repo.get_by_id(article_id)
            if not article:
                raise ValueError(f"Article not found: {article_id}")

            # Load essences
            snippets = snippet_repo.get_by_article_id(article_id)
            essences = [
                {
                    "category": s.category.value,
                    "content": s.content,
                    "tags": s.tags or [],
                }
                for s in snippets
            ]

            # Create initial state
            state = create_initial_state(
                article_id=article_id,
                seo_keywords=seo_keywords,
                target_persona=article.target_persona or "",
                article_title=article.title,
                tavily_profile=tavily_profile,
            )
            state["essences"] = essences

            # Update article status
            article.seo_keywords = seo_keywords
            article.status = ArticleStatus.RESEARCHING
            article_repo.update(article)

            if on_phase_change:
                on_phase_change("research")

        # Run research phase
        state = self._run_phase(state, "research", on_phase_change)

        # Update article with research results
        self._sync_research_to_db(article_id, state, seo_keywords)

        if on_phase_change:
            on_phase_change("waiting_input")

        return state

    def resume_after_input(
        self,
        article_id: str,
        state: ArticleState,
        on_phase_change: Callable[[str], None] | None = None,
    ) -> ArticleState:
        """
        Resume workflow after user input phase.

        Args:
            article_id: The article ID.
            state: Current workflow state with essences added.
            on_phase_change: Optional callback for phase changes.

        Returns:
            Final workflow state.
        """
        logger.info(f"Resuming workflow after input: {article_id}")

        # Update state phase
        state["phase"] = "drafting"

        if on_phase_change:
            on_phase_change("drafting")

        # Run drafting phase
        state = self._run_phase(state, "drafting", on_phase_change)

        # Update article with draft
        self._sync_draft_to_db(article_id, state)

        if on_phase_change:
            on_phase_change("review")

        # Run review phase
        state = self._run_phase(state, "review", on_phase_change)

        # Check if revision needed
        if state["review_score"] < 80 and state["retry_count"] < 1:
            logger.info("Score below threshold, initiating revision")
            state["phase"] = "revision"

            if on_phase_change:
                on_phase_change("revision")

            # Run revision
            state = self._run_phase(state, "drafting", on_phase_change)

            # Re-review
            state = self._run_phase(state, "review", on_phase_change)

        # Mark as complete
        state["phase"] = "complete"

        # Final sync to database
        self._sync_complete_to_db(article_id, state)

        if on_phase_change:
            on_phase_change("complete")

        return state

    def run_full_workflow(
        self,
        article_id: str,
        seo_keywords: str,
        essences: list[dict],
        on_phase_change: Callable[[str], None] | None = None,
        tavily_profile: str | None = None,
    ) -> ArticleState:
        """
        Run the complete workflow from start to finish.

        This is a convenience method that combines run_workflow
        and resume_after_input.

        Args:
            article_id: The article ID.
            seo_keywords: Target SEO keywords.
            essences: User-provided essences.
            on_phase_change: Optional callback for phase changes.

        Returns:
            Final workflow state.
        """
        # Run research phase
        state = self.run_workflow(
            article_id,
            seo_keywords,
            on_phase_change,
            tavily_profile=tavily_profile,
        )

        # Add essences and continue
        state["essences"] = essences

        # Resume with drafting
        return self.resume_after_input(article_id, state, on_phase_change)

    def _run_phase(
        self,
        state: ArticleState,
        phase: str,
        on_phase_change: Callable[[str], None] | None,
    ) -> ArticleState:
        """Run a single workflow phase."""
        from src.workflow.graph import (
            research_node,
            drafting_node,
            review_node,
        )

        phase_nodes = {
            "research": research_node,
            "drafting": drafting_node,
            "review": review_node,
        }

        node_func = phase_nodes.get(phase)
        if node_func:
            state = node_func(state)

        return state

    def _sync_research_to_db(self, article_id: str, state: ArticleState) -> None:
        """Sync research results to database."""
        with get_session() as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)

            if article:
                article.research_summary = state["research_summary"]
                article.competitor_analysis = {
                    "urls": state["competitor_urls"],
                    "content_gaps": state["content_gaps"],
                }
                article.outline_json = {
                    "suggested_outline": state["suggested_outline"],
                }
                article.status = ArticleStatus.WAITING_INPUT
                repo.update(article)

    def _sync_draft_to_db(self, article_id: str, state: ArticleState) -> None:
        """Sync draft results to database."""
        with get_session() as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)

            if article:
                article.draft_content_md = state["draft_content_md"]
                article.title_candidates = {"titles": state["title_candidates"]}
                article.image_prompts = {"prompts": state["image_prompts"]}
                article.sns_posts = state["sns_posts"]
                article.status = ArticleStatus.REVIEW
                repo.update(article)

    def _sync_complete_to_db(self, article_id: str, state: ArticleState) -> None:
        """Sync final results to database."""
        with get_session() as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)

            if article:
                article.draft_content_md = state["draft_content_md"]
                article.final_content_md = state["draft_content_md"]
                article.title_candidates = {"titles": state["title_candidates"]}
                article.image_prompts = {"prompts": state["image_prompts"]}
                article.sns_posts = state["sns_posts"]
                article.review_score = state["review_score"]
                article.review_feedback = state["review_feedback"]
                article.status = ArticleStatus.COMPLETED
                repo.update(article)

    # ===========================================
    # UI-oriented methods (individual phases)
    # ===========================================

    def run_research_only(
        self,
        article_id: str,
        seo_keywords: str,
        on_progress: Callable[[int, str], None] | None = None,
        tavily_profile: str | None = None,
    ) -> ArticleState:
        """
        Run only the research phase for an article.

        This method is designed for UI integration where research
        runs as a separate step before user input.

        Args:
            article_id: The article ID to process.
            seo_keywords: Target SEO keywords.
            on_progress: Optional callback for progress updates (percent, message).

        Returns:
            Workflow state after research phase.
        """
        logger.info(f"Running research phase for article: {article_id}")

        with get_session() as session:
            article_repo = ArticleRepository(session)

            # Load article
            article = article_repo.get_by_id(article_id)
            if not article:
                raise ValueError(f"Article not found: {article_id}")

            # Create initial state
            state = create_initial_state(
                article_id=article_id,
                seo_keywords=seo_keywords,
                target_persona=article.target_persona or "",
                article_title=article.title,
                tavily_profile=tavily_profile,
            )

            # Update article status
            article.seo_keywords = seo_keywords
            article.status = ArticleStatus.RESEARCHING
            article_repo.update(article)

        if on_progress:
            on_progress(10, "リサーチを開始...")

        # Run research phase
        state = self._run_phase(state, "research", None)

        if on_progress:
            on_progress(80, "リサーチ結果を保存中...")

        # Sync to database (includes competitor_analysis, outline_json)
        self._sync_research_to_db(article_id, state, seo_keywords)

        if on_progress:
            on_progress(100, "リサーチ完了")

        return state

    def run_generation_with_review(
        self,
        article_id: str,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> ArticleState:
        """
        Run drafting and review phases with Self-Correction loop.

        This method loads essences from DB, generates draft,
        runs review, and automatically revises if score < 80.

        Args:
            article_id: The article ID to process.
            on_progress: Optional callback for progress updates (percent, message).

        Returns:
            Final workflow state after completion.
        """
        logger.info(f"Running generation with review for article: {article_id}")

        with get_session() as session:
            article_repo = ArticleRepository(session)
            snippet_repo = SnippetRepository(session)

            # Load article
            article = article_repo.get_by_id(article_id)
            if not article:
                raise ValueError(f"Article not found: {article_id}")

            # Load essences
            snippets = list(snippet_repo.get_by_article_id(article_id))
            essences = [
                {
                    "category": s.category.value if hasattr(s.category, 'value') else str(s.category),
                    "content": s.content,
                    "tags": s.tags or [],
                }
                for s in snippets
            ]

            # Load research data from DB
            competitor_analysis = article.competitor_analysis or {}
            outline_json = article.outline_json or {}

            # Create state with research data
            state = create_initial_state(
                article_id=article_id,
                seo_keywords=article.seo_keywords or article.title,
                target_persona=article.target_persona or "",
                article_title=article.title,
            )
            state["essences"] = essences
            state["research_summary"] = article.research_summary or ""
            state["competitor_urls"] = competitor_analysis.get("urls", [])
            state["content_gaps"] = competitor_analysis.get("content_gaps", [])
            state["suggested_outline"] = outline_json.get("suggested_outline", [])

            # Update status
            article.status = ArticleStatus.DRAFTING
            article_repo.update(article)

        if on_progress:
            on_progress(10, "記事生成を開始...")

        # Run drafting phase
        state["phase"] = "drafting"
        state = self._run_phase(state, "drafting", None)

        if on_progress:
            on_progress(50, "記事生成完了、レビュー中...")

        # Sync draft to DB
        self._sync_draft_to_db(article_id, state)

        # Run review phase
        state = self._run_phase(state, "review", None)

        if on_progress:
            on_progress(70, f"レビュースコア: {state['review_score']}点")

        # Self-Correction loop
        from src.config import get_settings
        settings = get_settings()
        max_retries = settings.max_review_iterations

        if state["review_score"] < 80 and state["retry_count"] < max_retries:
            logger.info(f"Score {state['review_score']} < 80, initiating revision")

            if on_progress:
                on_progress(75, "スコア不足のため修正中...")

            state["phase"] = "revision"
            state = self._run_phase(state, "drafting", None)
            state = self._run_phase(state, "review", None)

            if on_progress:
                on_progress(90, f"修正後スコア: {state['review_score']}点")

        # Mark as complete
        state["phase"] = "complete"

        if on_progress:
            on_progress(95, "結果を保存中...")

        # Final sync to database
        self._sync_complete_to_db(article_id, state)

        if on_progress:
            on_progress(100, "完了")

        return state

    def _sync_research_to_db(
        self,
        article_id: str,
        state: ArticleState,
        seo_keywords: str | None = None,
    ) -> None:
        """Sync research results to database."""
        with get_session() as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)

            if article:
                article.research_summary = state["research_summary"]
                article.competitor_analysis = {
                    "urls": state["competitor_urls"],
                    "content_gaps": state["content_gaps"],
                    "generated_at": __import__("datetime").datetime.now().isoformat(),
                }
                article.outline_json = {
                    "suggested_outline": state["suggested_outline"],
                }
                if seo_keywords:
                    article.seo_keywords = seo_keywords
                article.status = ArticleStatus.WAITING_INPUT
                repo.update(article)

    def get_workflow_status(self, article_id: str) -> dict:
        """
        Get the current workflow status for an article.

        Args:
            article_id: The article ID.

        Returns:
            Dictionary with status information.
        """
        with get_session() as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)

            if not article:
                return {"error": "Article not found"}

            return {
                "article_id": article_id,
                "status": article.status.value,
                "has_research": bool(article.research_summary),
                "has_draft": bool(article.draft_content_md),
                "review_score": article.review_score,
                "is_uploaded": article.is_uploaded,
            }
