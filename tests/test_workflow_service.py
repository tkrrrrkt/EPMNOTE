"""
Unit tests for EPM Note Engine WorkflowService.

Tests the UI-oriented workflow methods with mocked dependencies.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.workflow.service import WorkflowService
from src.workflow.graph import ArticleState, create_initial_state
from src.database.models import Article, ArticleStatus, Snippet, SnippetCategory


# ============================================================================
# WorkflowService Tests
# ============================================================================

class TestWorkflowServiceInit:
    """Tests for WorkflowService initialization."""

    def test_init_creates_graph(self):
        """Test that service initializes with a workflow graph."""
        with patch("src.workflow.service.create_workflow_graph") as mock_create:
            mock_create.return_value = Mock()
            service = WorkflowService()
            assert service.graph is not None
            mock_create.assert_called_once()


class TestRunResearchOnly:
    """Tests for run_research_only method."""

    @pytest.fixture
    def mock_article(self):
        """Create a mock article."""
        article = Mock(spec=Article)
        article.id = "test-article-id"
        article.title = "テスト記事"
        article.target_persona = "経営企画部長"
        article.seo_keywords = None
        article.status = ArticleStatus.PLANNING
        return article

    @pytest.fixture
    def mock_research_state(self):
        """Create a mock research result state."""
        return {
            "article_id": "test-article-id",
            "phase": "waiting_input",
            "research_summary": "リサーチ結果のサマリー",
            "competitor_urls": ["https://example.com/1", "https://example.com/2"],
            "content_gaps": ["ギャップ1", "ギャップ2"],
            "suggested_outline": ["導入", "本論", "まとめ"],
        }

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_run_research_only_success(
        self, mock_repo_class, mock_get_session, mock_article, mock_research_state
    ):
        """Test successful research phase execution."""
        # Setup mocks
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_repo = Mock()
        mock_repo.get_by_id.return_value = mock_article
        mock_repo_class.return_value = mock_repo

        with patch("src.workflow.service.create_initial_state") as mock_create_state:
            mock_create_state.return_value = create_initial_state(
                article_id="test-article-id",
                seo_keywords="予算管理",
                target_persona="経営企画部長",
                article_title="テスト記事",
            )

            with patch.object(WorkflowService, "_run_phase") as mock_run_phase:
                mock_run_phase.return_value = mock_research_state

                with patch.object(WorkflowService, "_sync_research_to_db") as mock_sync:
                    service = WorkflowService()
                    result = service.run_research_only(
                        article_id="test-article-id",
                        seo_keywords="予算管理",
                    )

                    # Verify research phase was run
                    mock_run_phase.assert_called_once()
                    call_args = mock_run_phase.call_args
                    assert call_args[0][1] == "research"

                    # Verify DB sync was called
                    mock_sync.assert_called_once()
                    sync_args = mock_sync.call_args
                    assert sync_args[0][0] == "test-article-id"
                    assert sync_args[0][2] == "予算管理"

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_run_research_only_article_not_found(
        self, mock_repo_class, mock_get_session
    ):
        """Test error when article is not found."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_repo = Mock()
        mock_repo.get_by_id.return_value = None
        mock_repo_class.return_value = mock_repo

        service = WorkflowService()

        with pytest.raises(ValueError, match="Article not found"):
            service.run_research_only(
                article_id="nonexistent-id",
                seo_keywords="予算管理",
            )

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_run_research_only_progress_callback(
        self, mock_repo_class, mock_get_session, mock_article, mock_research_state
    ):
        """Test progress callback is called."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_repo = Mock()
        mock_repo.get_by_id.return_value = mock_article
        mock_repo_class.return_value = mock_repo

        progress_calls = []

        def on_progress(percent, message):
            progress_calls.append((percent, message))

        with patch("src.workflow.service.create_initial_state") as mock_create_state:
            mock_create_state.return_value = create_initial_state(
                article_id="test-article-id",
                seo_keywords="予算管理",
                target_persona="経営企画部長",
                article_title="テスト記事",
            )

            with patch.object(WorkflowService, "_run_phase") as mock_run_phase:
                mock_run_phase.return_value = mock_research_state

                with patch.object(WorkflowService, "_sync_research_to_db"):
                    service = WorkflowService()
                    service.run_research_only(
                        article_id="test-article-id",
                        seo_keywords="予算管理",
                        on_progress=on_progress,
                    )

                    # Verify progress callbacks were made
                    assert len(progress_calls) == 3
                    assert progress_calls[0][0] == 10
                    assert progress_calls[1][0] == 80
                    assert progress_calls[2][0] == 100


class TestRunGenerationWithReview:
    """Tests for run_generation_with_review method."""

    @pytest.fixture
    def mock_article_with_research(self):
        """Create a mock article with research completed."""
        article = Mock(spec=Article)
        article.id = "test-article-id"
        article.title = "テスト記事"
        article.target_persona = "経営企画部長"
        article.seo_keywords = "予算管理"
        article.status = ArticleStatus.WAITING_INPUT
        article.research_summary = "リサーチサマリー"
        article.competitor_analysis = {
            "urls": ["https://example.com/1"],
            "content_gaps": ["ギャップ1"],
        }
        article.outline_json = {
            "suggested_outline": ["導入", "本論", "まとめ"],
        }
        return article

    @pytest.fixture
    def mock_snippets(self):
        """Create mock snippets."""
        snippet = Mock(spec=Snippet)
        snippet.category = SnippetCategory.FAILURE
        snippet.content = "失敗談の内容"
        snippet.tags = ["タグ1"]
        return [snippet]

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    @patch("src.workflow.service.SnippetRepository")
    def test_run_generation_with_review_pass(
        self,
        mock_snippet_repo_class,
        mock_article_repo_class,
        mock_get_session,
        mock_article_with_research,
        mock_snippets,
    ):
        """Test generation with passing review score."""
        # Setup mocks
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_article_repo = Mock()
        mock_article_repo.get_by_id.return_value = mock_article_with_research
        mock_article_repo_class.return_value = mock_article_repo

        mock_snippet_repo = Mock()
        mock_snippet_repo.get_by_article_id.return_value = mock_snippets
        mock_snippet_repo_class.return_value = mock_snippet_repo

        def mock_run_phase(state, phase, callback):
            if phase == "drafting":
                state["draft_content_md"] = "# 生成された記事"
                state["title_candidates"] = ["タイトル1"]
                state["image_prompts"] = []
                state["sns_posts"] = {"x": "投稿"}
            elif phase == "review":
                state["review_score"] = 85  # Passing score
                state["review_feedback"] = "良い記事です"
                state["score_breakdown"] = {}
            return state

        with patch.object(WorkflowService, "_run_phase", side_effect=mock_run_phase):
            with patch.object(WorkflowService, "_sync_draft_to_db"):
                with patch.object(WorkflowService, "_sync_complete_to_db"):
                    with patch("src.config.get_settings") as mock_settings:
                        mock_settings.return_value = Mock(max_review_iterations=1)
                        service = WorkflowService()
                        result = service.run_generation_with_review(
                            article_id="test-article-id",
                        )

                        assert result["review_score"] == 85
                        assert result["phase"] == "complete"

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    @patch("src.workflow.service.SnippetRepository")
    def test_run_generation_with_self_correction(
        self,
        mock_snippet_repo_class,
        mock_article_repo_class,
        mock_get_session,
        mock_article_with_research,
        mock_snippets,
    ):
        """Test generation with Self-Correction loop."""
        # Setup mocks
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_article_repo = Mock()
        mock_article_repo.get_by_id.return_value = mock_article_with_research
        mock_article_repo_class.return_value = mock_article_repo

        mock_snippet_repo = Mock()
        mock_snippet_repo.get_by_article_id.return_value = mock_snippets
        mock_snippet_repo_class.return_value = mock_snippet_repo

        call_count = {"drafting": 0, "review": 0}

        def mock_run_phase(state, phase, callback):
            if phase == "drafting":
                call_count["drafting"] += 1
                state["draft_content_md"] = f"# 記事 v{call_count['drafting']}"
                state["title_candidates"] = ["タイトル1"]
                state["image_prompts"] = []
                state["sns_posts"] = {"x": "投稿"}
                if call_count["drafting"] > 1:
                    state["retry_count"] = state.get("retry_count", 0) + 1
            elif phase == "review":
                call_count["review"] += 1
                if call_count["review"] == 1:
                    # First review: failing score
                    state["review_score"] = 70
                    state["review_feedback"] = "改善が必要"
                else:
                    # Second review: passing score
                    state["review_score"] = 82
                    state["review_feedback"] = "改善されました"
                state["score_breakdown"] = {}
            return state

        with patch.object(WorkflowService, "_run_phase", side_effect=mock_run_phase):
            with patch.object(WorkflowService, "_sync_draft_to_db"):
                with patch.object(WorkflowService, "_sync_complete_to_db"):
                    with patch("src.config.get_settings") as mock_settings:
                        mock_settings.return_value = Mock(max_review_iterations=1)
                        service = WorkflowService()
                        result = service.run_generation_with_review(
                            article_id="test-article-id",
                        )

                        # Verify Self-Correction was triggered
                        assert call_count["drafting"] == 2  # Initial + revision
                        assert call_count["review"] == 2    # Initial + re-review
                        assert result["review_score"] == 82
                        assert result["phase"] == "complete"

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    @patch("src.workflow.service.SnippetRepository")
    def test_run_generation_max_retries_reached(
        self,
        mock_snippet_repo_class,
        mock_article_repo_class,
        mock_get_session,
        mock_article_with_research,
        mock_snippets,
    ):
        """Test that max retries limit is respected."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_article_repo = Mock()
        mock_article_repo.get_by_id.return_value = mock_article_with_research
        mock_article_repo_class.return_value = mock_article_repo

        mock_snippet_repo = Mock()
        mock_snippet_repo.get_by_article_id.return_value = mock_snippets
        mock_snippet_repo_class.return_value = mock_snippet_repo

        call_count = {"drafting": 0, "review": 0}

        def mock_run_phase(state, phase, callback):
            if phase == "drafting":
                call_count["drafting"] += 1
                state["draft_content_md"] = "# 記事"
                state["title_candidates"] = []
                state["image_prompts"] = []
                state["sns_posts"] = {}
            elif phase == "review":
                call_count["review"] += 1
                state["review_score"] = 70  # Always failing
                state["review_feedback"] = "改善が必要"
                state["score_breakdown"] = {}
            return state

        with patch.object(WorkflowService, "_run_phase", side_effect=mock_run_phase):
            with patch.object(WorkflowService, "_sync_draft_to_db"):
                with patch.object(WorkflowService, "_sync_complete_to_db"):
                    # Set max_review_iterations to 0 (no retries allowed)
                    with patch("src.config.get_settings") as mock_settings:
                        mock_settings.return_value = Mock(max_review_iterations=0)
                        service = WorkflowService()
                        result = service.run_generation_with_review(
                            article_id="test-article-id",
                        )

                        # No Self-Correction should happen
                        assert call_count["drafting"] == 1
                        assert call_count["review"] == 1
                        assert result["review_score"] == 70
                        assert result["phase"] == "complete"


class TestSyncResearchToDb:
    """Tests for _sync_research_to_db method."""

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_sync_research_saves_all_fields(
        self, mock_repo_class, mock_get_session
    ):
        """Test that research data is properly saved to DB."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_article = Mock()
        mock_repo = Mock()
        mock_repo.get_by_id.return_value = mock_article
        mock_repo_class.return_value = mock_repo

        state = {
            "research_summary": "リサーチサマリー",
            "competitor_urls": ["https://example.com/1"],
            "content_gaps": ["ギャップ1"],
            "suggested_outline": ["導入", "本論"],
        }

        service = WorkflowService()
        service._sync_research_to_db("test-id", state, "予算管理")

        # Verify article fields were updated
        assert mock_article.research_summary == "リサーチサマリー"
        assert "urls" in mock_article.competitor_analysis
        assert mock_article.competitor_analysis["urls"] == ["https://example.com/1"]
        assert "content_gaps" in mock_article.competitor_analysis
        assert "generated_at" in mock_article.competitor_analysis
        assert mock_article.outline_json["suggested_outline"] == ["導入", "本論"]
        assert mock_article.seo_keywords == "予算管理"
        assert mock_article.status == ArticleStatus.WAITING_INPUT

        # Verify update was called
        mock_repo.update.assert_called_once_with(mock_article)


class TestGetWorkflowStatus:
    """Tests for get_workflow_status method."""

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_get_status_existing_article(self, mock_repo_class, mock_get_session):
        """Test getting status for existing article."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_article = Mock()
        mock_article.status = ArticleStatus.COMPLETED
        mock_article.research_summary = "サマリー"
        mock_article.draft_content_md = "# 記事"
        mock_article.review_score = 85
        mock_article.is_uploaded = True

        mock_repo = Mock()
        mock_repo.get_by_id.return_value = mock_article
        mock_repo_class.return_value = mock_repo

        service = WorkflowService()
        status = service.get_workflow_status("test-id")

        assert status["article_id"] == "test-id"
        assert status["status"].lower() == "completed"
        assert status["has_research"] is True
        assert status["has_draft"] is True
        assert status["review_score"] == 85
        assert status["is_uploaded"] is True

    @patch("src.workflow.service.get_session")
    @patch("src.workflow.service.ArticleRepository")
    def test_get_status_not_found(self, mock_repo_class, mock_get_session):
        """Test getting status for non-existent article."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=None)

        mock_repo = Mock()
        mock_repo.get_by_id.return_value = None
        mock_repo_class.return_value = mock_repo

        service = WorkflowService()
        status = service.get_workflow_status("nonexistent-id")

        assert "error" in status
        assert status["error"] == "Article not found"
