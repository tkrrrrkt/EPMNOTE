"""
Unit tests for EPM Note Engine workflow.

Tests the LangGraph workflow orchestration with mocked agents.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from src.agents.workflow import (
    ArticleState,
    research_node,
    writing_node,
    review_node,
    should_revise,
    create_workflow,
    run_article_generation,
)
from src.agents.research_agent import ResearchResult, CompetitorAnalysis
from src.agents.writer_agent import DraftResult
from src.agents.reviewer_agent import ReviewResult, ScoreBreakdown


# ============================================================================
# ArticleState Tests
# ============================================================================

class TestArticleState:
    """Tests for ArticleState dataclass."""

    def test_default_values(self):
        """Test default state values."""
        state = ArticleState()

        assert state.article_id == ""
        assert state.article_title == ""
        assert state.revision_count == 0
        assert state.max_revisions == 2
        assert state.current_phase == "research"
        assert state.error is None

    def test_custom_initialization(self):
        """Test custom state initialization."""
        state = ArticleState(
            article_id="test-123",
            article_title="テスト記事",
            seo_keywords="予算管理",
            target_persona="経営企画部長",
            max_revisions=3,
        )

        assert state.article_id == "test-123"
        assert state.article_title == "テスト記事"
        assert state.max_revisions == 3


# ============================================================================
# Research Node Tests
# ============================================================================

class TestResearchNode:
    """Tests for research_node function."""

    @pytest.fixture
    def mock_research_result(self):
        """Create a mock research result."""
        return ResearchResult(
            competitor_analysis=CompetitorAnalysis(
                urls=["https://example.com/1"],
                headings=[["見出し1"]],
                content_gaps=["差別化ポイント"],
                key_points=["キーポイント"],
            ),
            internal_references=["内部参照"],
            suggested_outline=["導入", "本論", "まとめ"],
            research_summary="リサーチサマリー",
        )

    @patch("src.agents.workflow.ResearchAgent")
    def test_research_node_success(self, mock_agent_class, mock_research_result):
        """Test successful research node execution."""
        mock_agent = Mock()
        mock_agent.analyze.return_value = mock_research_result
        mock_agent_class.return_value = mock_agent

        state = ArticleState(seo_keywords="予算管理")
        result = research_node(state)

        assert result["research_result"] == mock_research_result
        assert result["research_summary"] == "リサーチサマリー"
        assert result["current_phase"] == "writing"

    @patch("src.agents.workflow.ResearchAgent")
    def test_research_node_failure(self, mock_agent_class):
        """Test research node error handling."""
        mock_agent = Mock()
        mock_agent.analyze.side_effect = Exception("API Error")
        mock_agent_class.return_value = mock_agent

        state = ArticleState(seo_keywords="予算管理")
        result = research_node(state)

        assert "error" in result
        assert "リサーチに失敗しました" in result["error"]
        assert result["current_phase"] == "error"


# ============================================================================
# Writing Node Tests
# ============================================================================

class TestWritingNode:
    """Tests for writing_node function."""

    @pytest.fixture
    def mock_draft_result(self):
        """Create a mock draft result."""
        return DraftResult(
            draft_content_md="# 記事タイトル\n\nコンテンツ",
            title_candidates=["タイトル1", "タイトル2"],
            sns_posts={"x": "Xの投稿", "linkedin": "LinkedInの投稿"},
        )

    @pytest.fixture
    def state_with_research(self):
        """Create state with research completed."""
        return ArticleState(
            article_title="テスト記事",
            target_persona="経営企画部長",
            research_result=ResearchResult(
                competitor_analysis=CompetitorAnalysis(
                    content_gaps=["差別化ポイント"],
                ),
                suggested_outline=["導入", "本論"],
                research_summary="サマリー",
            ),
            essences=[{"category": "体験談", "content": "経験"}],
        )

    @patch("src.agents.workflow.WriterAgent")
    def test_writing_node_initial_draft(
        self, mock_agent_class, mock_draft_result, state_with_research
    ):
        """Test initial draft generation."""
        mock_agent = Mock()
        mock_agent.generate_draft.return_value = mock_draft_result
        mock_agent_class.return_value = mock_agent

        result = writing_node(state_with_research)

        assert result["draft_result"] == mock_draft_result
        assert "記事タイトル" in result["draft_content_md"]
        assert len(result["title_candidates"]) == 2
        assert result["current_phase"] == "review"
        mock_agent.generate_draft.assert_called_once()

    @patch("src.agents.workflow.WriterAgent")
    def test_writing_node_revision(self, mock_agent_class, state_with_research):
        """Test draft revision."""
        state_with_research.revision_count = 1
        state_with_research.draft_content_md = "# 元の記事"
        state_with_research.review_feedback = "改善してください"
        state_with_research.review_result = ReviewResult(
            score=70,
            breakdown=ScoreBreakdown(target_appeal=20, logical_structure=30, seo_fitness=20),
            feedback="フィードバック",
        )
        state_with_research.title_candidates = ["既存タイトル"]
        state_with_research.sns_posts = {"x": "既存"}

        mock_agent = Mock()
        mock_agent.revise_draft.return_value = "# 改善後の記事"
        mock_agent_class.return_value = mock_agent

        result = writing_node(state_with_research)

        assert "改善後" in result["draft_content_md"]
        mock_agent.revise_draft.assert_called_once()

    @patch("src.agents.workflow.WriterAgent")
    def test_writing_node_failure(self, mock_agent_class, state_with_research):
        """Test writing node error handling."""
        mock_agent = Mock()
        mock_agent.generate_draft.side_effect = Exception("API Error")
        mock_agent_class.return_value = mock_agent

        result = writing_node(state_with_research)

        assert "error" in result
        assert "記事生成に失敗しました" in result["error"]
        assert result["current_phase"] == "error"


# ============================================================================
# Review Node Tests
# ============================================================================

class TestReviewNode:
    """Tests for review_node function."""

    @pytest.fixture
    def state_with_draft(self):
        """Create state with draft completed."""
        return ArticleState(
            draft_content_md="# 記事\n\nコンテンツ",
            target_persona="経営企画部長",
            seo_keywords="予算管理",
        )

    @patch("src.agents.workflow.ReviewerAgent")
    def test_review_node_pass(self, mock_agent_class, state_with_draft):
        """Test review with passing score."""
        mock_result = ReviewResult(
            score=85,
            breakdown=ScoreBreakdown(target_appeal=28, logical_structure=35, seo_fitness=22),
            feedback="良い記事です",
            passed=True,
        )
        mock_agent = Mock()
        mock_agent.review.return_value = mock_result
        mock_agent_class.return_value = mock_agent

        result = review_node(state_with_draft)

        assert result["review_score"] == 85
        assert result["review_passed"] is True
        assert result["revision_count"] == 1
        assert result["current_phase"] == "decision"

    @patch("src.agents.workflow.ReviewerAgent")
    def test_review_node_fail(self, mock_agent_class, state_with_draft):
        """Test review with failing score."""
        mock_result = ReviewResult(
            score=65,
            breakdown=ScoreBreakdown(target_appeal=18, logical_structure=28, seo_fitness=19),
            feedback="改善が必要です",
            passed=False,
        )
        mock_agent = Mock()
        mock_agent.review.return_value = mock_result
        mock_agent_class.return_value = mock_agent

        result = review_node(state_with_draft)

        assert result["review_score"] == 65
        assert result["review_passed"] is False

    @patch("src.agents.workflow.ReviewerAgent")
    def test_review_node_error(self, mock_agent_class, state_with_draft):
        """Test review node error handling."""
        mock_agent = Mock()
        mock_agent.review.side_effect = Exception("API Error")
        mock_agent_class.return_value = mock_agent

        result = review_node(state_with_draft)

        assert "error" in result
        assert "レビューに失敗しました" in result["error"]


# ============================================================================
# Decision Logic Tests
# ============================================================================

class TestShouldRevise:
    """Tests for should_revise decision function."""

    def test_complete_on_pass(self):
        """Test completion on passing review."""
        state = ArticleState(review_passed=True, review_score=85)
        assert should_revise(state) == "complete"

    def test_revise_on_fail(self):
        """Test revision on failing review."""
        state = ArticleState(review_passed=False, review_score=70, revision_count=1)
        assert should_revise(state) == "revise"

    def test_complete_on_max_revisions(self):
        """Test completion on max revisions reached."""
        state = ArticleState(
            review_passed=False,
            review_score=70,
            revision_count=2,
            max_revisions=2,
        )
        assert should_revise(state) == "complete"

    def test_error_on_error_state(self):
        """Test error routing on error state."""
        state = ArticleState(error="Something went wrong")
        assert should_revise(state) == "error"


# ============================================================================
# Workflow Creation Tests
# ============================================================================

class TestCreateWorkflow:
    """Tests for workflow creation."""

    def test_workflow_compiles(self):
        """Test that workflow compiles without errors."""
        workflow = create_workflow()
        assert workflow is not None

    def test_workflow_has_nodes(self):
        """Test that workflow has expected nodes."""
        from src.agents.workflow import article_workflow

        # The compiled workflow should exist
        assert article_workflow is not None


# ============================================================================
# Integration Tests (with mocks)
# ============================================================================

class TestRunArticleGeneration:
    """Integration tests for run_article_generation."""

    @patch("src.agents.workflow.article_workflow")
    def test_run_article_generation_success(self, mock_workflow):
        """Test successful article generation."""
        mock_workflow.invoke.return_value = {
            "article_id": "test-123",
            "article_title": "テスト記事",
            "seo_keywords": "予算管理",
            "target_persona": "経営企画部長",
            "essences": [],
            "research_result": None,
            "research_summary": "サマリー",
            "draft_result": None,
            "draft_content_md": "# 記事",
            "title_candidates": ["タイトル"],
            "sns_posts": {},
            "review_result": None,
            "review_score": 85,
            "review_feedback": "良い",
            "review_passed": True,
            "revision_count": 1,
            "max_revisions": 2,
            "current_phase": "complete",
            "error": None,
        }

        result = run_article_generation(
            article_id="test-123",
            article_title="テスト記事",
            seo_keywords="予算管理",
            target_persona="経営企画部長",
        )

        assert isinstance(result, ArticleState)
        assert result.review_passed is True
        assert result.review_score == 85

    @patch("src.agents.workflow.article_workflow")
    def test_run_article_generation_with_essences(self, mock_workflow):
        """Test article generation with essences."""
        mock_workflow.invoke.return_value = {
            "article_id": "test-123",
            "article_title": "テスト記事",
            "seo_keywords": "予算管理",
            "target_persona": "経営企画部長",
            "essences": [{"category": "体験談", "content": "経験"}],
            "research_result": None,
            "research_summary": "",
            "draft_result": None,
            "draft_content_md": "",
            "title_candidates": [],
            "sns_posts": {},
            "review_result": None,
            "review_score": 0,
            "review_feedback": "",
            "review_passed": False,
            "revision_count": 0,
            "max_revisions": 2,
            "current_phase": "research",
            "error": None,
        }

        essences = [{"category": "体験談", "content": "経験"}]
        result = run_article_generation(
            article_id="test-123",
            article_title="テスト記事",
            seo_keywords="予算管理",
            target_persona="経営企画部長",
            essences=essences,
        )

        # Verify invoke was called with correct initial state
        call_args = mock_workflow.invoke.call_args
        initial_state = call_args[0][0]
        assert len(initial_state.essences) == 1
