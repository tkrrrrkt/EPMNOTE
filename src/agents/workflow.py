"""
EPM Note Engine - Article Generation Workflow

LangGraph-based workflow orchestrating Research, Writer, and Reviewer agents.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

from langgraph.graph import StateGraph, END

from src.agents.research_agent import ResearchAgent, ResearchResult
from src.agents.writer_agent import WriterAgent, DraftResult
from src.agents.reviewer_agent import ReviewerAgent, ReviewResult

logger = logging.getLogger(__name__)


@dataclass
class ArticleState:
    """State for the article generation workflow."""

    # Input
    article_id: str = ""
    article_title: str = ""
    seo_keywords: str = ""
    target_persona: str = ""
    essences: list[dict] = field(default_factory=list)

    # Research phase output
    research_result: ResearchResult | None = None
    research_summary: str = ""

    # Writing phase output
    draft_result: DraftResult | None = None
    draft_content_md: str = ""
    title_candidates: list[str] = field(default_factory=list)
    sns_posts: dict[str, str] = field(default_factory=dict)

    # Review phase output
    review_result: ReviewResult | None = None
    review_score: int = 0
    review_feedback: str = ""
    review_passed: bool = False

    # Workflow control
    revision_count: int = 0
    max_revisions: int = 2
    current_phase: str = "research"
    error: str | None = None


def research_node(state: ArticleState) -> dict:
    """Execute research phase."""
    logger.info(f"[Research] Starting for: {state.seo_keywords}")

    try:
        agent = ResearchAgent()
        result = agent.analyze(state.seo_keywords)

        return {
            "research_result": result,
            "research_summary": result.research_summary,
            "current_phase": "writing",
        }
    except Exception as e:
        logger.error(f"[Research] Failed: {e}")
        return {
            "error": f"リサーチに失敗しました: {str(e)}",
            "current_phase": "error",
        }


def writing_node(state: ArticleState) -> dict:
    """Execute writing phase."""
    logger.info(f"[Writing] Generating draft for: {state.article_title}")

    try:
        agent = WriterAgent()

        if state.revision_count == 0:
            # Initial draft generation
            result = agent.generate_draft(
                research_result=state.research_result,
                essences=state.essences,
                target_persona=state.target_persona,
                article_title=state.article_title,
            )
        else:
            # Revision based on feedback
            revised_content = agent.revise_draft(
                original_content=state.draft_content_md,
                feedback=state.review_feedback,
                score_breakdown={
                    "target_appeal": state.review_result.breakdown.target_appeal if state.review_result else 0,
                    "logical_structure": state.review_result.breakdown.logical_structure if state.review_result else 0,
                    "seo_fitness": state.review_result.breakdown.seo_fitness if state.review_result else 0,
                },
            )
            result = DraftResult(
                draft_content_md=revised_content,
                title_candidates=state.title_candidates,
                sns_posts=state.sns_posts,
            )

        return {
            "draft_result": result,
            "draft_content_md": result.draft_content_md,
            "title_candidates": result.title_candidates or state.title_candidates,
            "sns_posts": result.sns_posts or state.sns_posts,
            "current_phase": "review",
        }
    except Exception as e:
        logger.error(f"[Writing] Failed: {e}")
        return {
            "error": f"記事生成に失敗しました: {str(e)}",
            "current_phase": "error",
        }


def review_node(state: ArticleState) -> dict:
    """Execute review phase."""
    logger.info(f"[Review] Evaluating draft (revision {state.revision_count})")

    try:
        agent = ReviewerAgent()
        result = agent.review(
            draft_content=state.draft_content_md,
            target_persona=state.target_persona,
            seo_keywords=state.seo_keywords,
        )

        return {
            "review_result": result,
            "review_score": result.score,
            "review_feedback": result.feedback,
            "review_passed": result.passed,
            "revision_count": state.revision_count + 1,
            "current_phase": "decision",
        }
    except Exception as e:
        logger.error(f"[Review] Failed: {e}")
        return {
            "error": f"レビューに失敗しました: {str(e)}",
            "current_phase": "error",
        }


def should_revise(state: ArticleState) -> Literal["revise", "complete", "error"]:
    """Determine if revision is needed."""
    if state.error:
        return "error"

    if state.review_passed:
        logger.info(f"[Decision] Review passed with score {state.review_score}")
        return "complete"

    if state.revision_count >= state.max_revisions:
        logger.info(f"[Decision] Max revisions reached ({state.max_revisions})")
        return "complete"

    logger.info(f"[Decision] Review failed (score {state.review_score}), revising...")
    return "revise"


def create_workflow() -> StateGraph:
    """Create the article generation workflow."""
    workflow = StateGraph(ArticleState)

    # Add nodes
    workflow.add_node("research", research_node)
    workflow.add_node("writing", writing_node)
    workflow.add_node("review", review_node)

    # Add edges
    workflow.set_entry_point("research")
    workflow.add_edge("research", "writing")
    workflow.add_edge("writing", "review")

    # Add conditional edge for review decision
    workflow.add_conditional_edges(
        "review",
        should_revise,
        {
            "revise": "writing",
            "complete": END,
            "error": END,
        },
    )

    return workflow.compile()


# Compiled workflow instance
article_workflow = create_workflow()


def run_article_generation(
    article_id: str,
    article_title: str,
    seo_keywords: str,
    target_persona: str,
    essences: list[dict] | None = None,
    max_revisions: int = 2,
) -> ArticleState:
    """
    Run the complete article generation workflow.

    Args:
        article_id: Database ID of the article.
        article_title: Title of the article.
        seo_keywords: SEO keywords to target.
        target_persona: Target reader persona.
        essences: User-provided essence snippets.
        max_revisions: Maximum number of revision attempts.

    Returns:
        Final ArticleState with all results.
    """
    initial_state = ArticleState(
        article_id=article_id,
        article_title=article_title,
        seo_keywords=seo_keywords,
        target_persona=target_persona,
        essences=essences or [],
        max_revisions=max_revisions,
    )

    logger.info(f"Starting article generation workflow for: {article_title}")

    # Run workflow
    final_state = article_workflow.invoke(initial_state)

    logger.info(
        f"Workflow completed. Score: {final_state['review_score']}, "
        f"Passed: {final_state['review_passed']}, "
        f"Revisions: {final_state['revision_count']}"
    )

    # Convert dict back to ArticleState
    return ArticleState(**final_state)
