"""
EPM Note Engine - LangGraph Workflow Definition

Defines the article generation workflow using LangGraph StateGraph.
"""

import logging
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class ArticleState(TypedDict):
    """
    State for the article generation workflow.

    This TypedDict defines all the data that flows through the workflow.
    """

    # Article identification
    article_id: str

    # Current phase
    phase: Literal[
        "research",
        "waiting_input",
        "drafting",
        "review",
        "revision",
        "complete",
    ]

    # Input data
    seo_keywords: str
    target_persona: str
    article_title: str
    tavily_profile: str

    # Research results
    research_summary: str
    competitor_urls: list[str]
    content_gaps: list[str]
    suggested_outline: list[str]

    # User essences
    essences: list[dict]

    # Draft content
    draft_content_md: str
    title_candidates: list[str]
    image_prompts: list[str]
    sns_posts: dict[str, str]

    # Review results
    review_score: int
    review_feedback: str
    score_breakdown: dict

    # Control flow
    retry_count: int
    error_message: str


def create_initial_state(
    article_id: str,
    seo_keywords: str,
    target_persona: str,
    article_title: str,
    tavily_profile: str | None = None,
) -> ArticleState:
    """
    Create an initial workflow state.

    Args:
        article_id: The article ID.
        seo_keywords: Target SEO keywords.
        target_persona: Target reader persona.
        article_title: Base article title.

    Returns:
        Initial ArticleState.
    """
    return ArticleState(
        article_id=article_id,
        phase="research",
        seo_keywords=seo_keywords,
        target_persona=target_persona,
        article_title=article_title,
        tavily_profile=tavily_profile or "",
        research_summary="",
        competitor_urls=[],
        content_gaps=[],
        suggested_outline=[],
        essences=[],
        draft_content_md="",
        title_candidates=[],
        image_prompts=[],
        sns_posts={},
        review_score=0,
        review_feedback="",
        score_breakdown={},
        retry_count=0,
        error_message="",
    )


# ===========================================
# Node Functions
# ===========================================


def research_node(state: ArticleState) -> ArticleState:
    """
    Execute research phase.

    Uses ResearchAgent to analyze competitors and internal knowledge.
    """
    logger.info(f"Research node: article_id={state['article_id']}")

    from src.agents.research_agent import ResearchAgent
    from src.repositories.rag_service import RAGService

    try:
        rag_service = RAGService()
        agent = ResearchAgent(rag_service)

        profile = state.get("tavily_profile") or None
        result = agent.analyze(state["seo_keywords"], domain_profile=profile)

        return {
            **state,
            "phase": "waiting_input",
            "research_summary": result.research_summary,
            "competitor_urls": result.competitor_analysis.urls,
            "content_gaps": result.competitor_analysis.content_gaps,
            "suggested_outline": result.suggested_outline,
        }

    except Exception as e:
        logger.error(f"Research failed: {e}")
        return {
            **state,
            "error_message": f"リサーチに失敗しました: {e}",
        }


def drafting_node(state: ArticleState) -> ArticleState:
    """
    Execute drafting phase.

    Uses WriterAgent to generate article content.
    """
    logger.info(f"Drafting node: article_id={state['article_id']}")

    from src.agents.writer_agent import WriterAgent
    from src.agents.research_agent import ResearchResult, CompetitorAnalysis

    try:
        agent = WriterAgent()

        # Reconstruct research result
        research_result = ResearchResult(
            competitor_analysis=CompetitorAnalysis(
                urls=state["competitor_urls"],
                content_gaps=state["content_gaps"],
            ),
            suggested_outline=state["suggested_outline"],
            research_summary=state["research_summary"],
        )

        # Check if this is a revision
        if state["phase"] == "revision" and state["draft_content_md"]:
            # Revise existing draft
            revised_content = agent.revise_draft(
                original_content=state["draft_content_md"],
                feedback=state["review_feedback"],
                score_breakdown=state["score_breakdown"],
            )
            return {
                **state,
                "phase": "review",
                "draft_content_md": revised_content,
                "retry_count": state["retry_count"] + 1,
            }
        else:
            # Generate new draft
            result = agent.generate_draft(
                research_result=research_result,
                essences=state["essences"],
                target_persona=state["target_persona"],
                article_title=state["article_title"],
            )

            return {
                **state,
                "phase": "review",
                "draft_content_md": result.draft_content_md,
                "title_candidates": result.title_candidates,
                "image_prompts": result.image_prompts,
                "sns_posts": result.sns_posts,
            }

    except Exception as e:
        logger.error(f"Drafting failed: {e}")
        return {
            **state,
            "error_message": f"記事生成に失敗しました: {e}",
        }


def review_node(state: ArticleState) -> ArticleState:
    """
    Execute review phase.

    Uses ReviewerAgent to evaluate article quality.
    """
    logger.info(f"Review node: article_id={state['article_id']}")

    from src.agents.reviewer_agent import ReviewerAgent

    try:
        agent = ReviewerAgent()

        result = agent.review(
            draft_content=state["draft_content_md"],
            target_persona=state["target_persona"],
            seo_keywords=state["seo_keywords"],
        )

        return {
            **state,
            "review_score": result.score,
            "review_feedback": result.feedback,
            "score_breakdown": {
                "target_appeal": result.breakdown.target_appeal,
                "logical_structure": result.breakdown.logical_structure,
                "seo_fitness": result.breakdown.seo_fitness,
            },
        }

    except Exception as e:
        logger.error(f"Review failed: {e}")
        return {
            **state,
            "error_message": f"レビューに失敗しました: {e}",
        }


# ===========================================
# Conditional Edge Functions
# ===========================================


def should_revise(state: ArticleState) -> Literal["revision", "complete"]:
    """
    Determine if the article needs revision.

    Args:
        state: Current workflow state.

    Returns:
        "revision" if score < 80 and retry_count < 1, else "complete".
    """
    from src.config import get_settings

    settings = get_settings()
    max_retries = settings.max_review_iterations

    if state["review_score"] < 80 and state["retry_count"] < max_retries:
        logger.info(
            f"Review score {state['review_score']} < 80, "
            f"retry {state['retry_count']+1}/{max_retries}"
        )
        return "revision"
    else:
        logger.info(f"Review passed or max retries reached, completing workflow")
        return "complete"


def complete_node(state: ArticleState) -> ArticleState:
    """
    Mark workflow as complete.
    """
    return {
        **state,
        "phase": "complete",
    }


# ===========================================
# Graph Construction
# ===========================================


def create_workflow_graph() -> StateGraph:
    """
    Create the article generation workflow graph.

    Returns:
        Compiled StateGraph for the workflow.
    """
    # Create graph with ArticleState
    workflow = StateGraph(ArticleState)

    # Add nodes
    workflow.add_node("research", research_node)
    workflow.add_node("drafting", drafting_node)
    workflow.add_node("review", review_node)
    workflow.add_node("complete", complete_node)

    # Set entry point
    workflow.set_entry_point("research")

    # Add edges
    workflow.add_edge("research", "drafting")  # After research, wait for input then draft
    workflow.add_edge("drafting", "review")

    # Conditional edge after review
    workflow.add_conditional_edges(
        "review",
        should_revise,
        {
            "revision": "drafting",
            "complete": "complete",
        },
    )

    # Complete is terminal
    workflow.add_edge("complete", END)

    return workflow.compile()
