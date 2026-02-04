"""
Unit tests for LinkService.

Tests internal link suggestion functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.services.link_service import (
    LinkService,
    LinkSuggestion,
    LinkSuggestionResult,
)


class TestLinkService:
    """Tests for LinkService."""

    def test_link_suggestion_dataclass(self):
        """Test LinkSuggestion dataclass creation."""
        suggestion = LinkSuggestion(
            article_id="test-id",
            title="テスト記事",
            url="https://note.com/test",
            relevance_score=0.85,
            snippet="これはテスト記事です...",
        )
        assert suggestion.article_id == "test-id"
        assert suggestion.title == "テスト記事"
        assert suggestion.relevance_score == 0.85

    def test_link_suggestion_result_to_dict(self):
        """Test LinkSuggestionResult.to_dict() method."""
        suggestion = LinkSuggestion(
            article_id="id1",
            title="記事1",
            url=None,
            relevance_score=0.9,
        )
        result = LinkSuggestionResult(
            suggestions=[suggestion],
            source_keywords=["予算管理", "FP&A"],
        )

        d = result.to_dict()
        assert len(d["suggestions"]) == 1
        assert d["suggestions"][0]["article_id"] == "id1"
        assert d["source_keywords"] == ["予算管理", "FP&A"]
        assert d["error"] == ""

    def test_extract_keywords_from_headings(self):
        """Test keyword extraction from markdown headings."""
        service = LinkService()
        content = """
## 予算管理の基本

### なぜ予算管理が重要か

**FP&A**の役割は大きい。

## Excelの限界
"""
        keywords = service._extract_keywords(content)

        assert len(keywords) > 0
        assert "予算管理の基本" in keywords or "予算管理" in " ".join(keywords)

    def test_extract_keywords_from_bold_text(self):
        """Test keyword extraction from bold text."""
        service = LinkService()
        content = """
これは**重要なポイント**です。
また**SSoT**という概念も重要です。
"""
        keywords = service._extract_keywords(content)

        # Should extract bold text as keywords
        assert any("SSoT" in kw for kw in keywords)

    def test_extract_keywords_empty_content(self):
        """Test keyword extraction with empty content."""
        service = LinkService()
        keywords = service._extract_keywords("")

        assert keywords == []

    @patch("src.services.link_service.get_session")
    def test_suggest_internal_links_no_articles(self, mock_get_session):
        """Test link suggestion when no related articles exist."""
        mock_session = MagicMock()
        mock_repo = Mock()
        mock_repo.get_all.return_value = []
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        with patch("src.services.link_service.ArticleRepository", return_value=mock_repo):
            service = LinkService()
            result = service.suggest_internal_links(
                "## 予算管理\n\n予算管理の基本について解説します。"
            )

            assert isinstance(result, LinkSuggestionResult)
            assert len(result.suggestions) == 0

    def test_calculate_relevance_title_match(self):
        """Test relevance calculation with title match."""
        service = LinkService()

        mock_article = Mock()
        mock_article.title = "予算管理の基本ガイド"
        mock_article.seo_keywords = "予算, 管理"
        mock_article.draft_content_md = "記事内容..."

        keywords = ["予算管理", "ガイド"]
        score = service._calculate_relevance(mock_article, keywords)

        # Should have high score due to title match
        assert score > 0.5

    def test_calculate_relevance_no_match(self):
        """Test relevance calculation with no keyword match."""
        service = LinkService()

        mock_article = Mock()
        mock_article.title = "マーケティング戦略"
        mock_article.seo_keywords = "広告, マーケ"
        mock_article.draft_content_md = "マーケティングについて..."

        keywords = ["予算管理", "FP&A", "経理"]
        score = service._calculate_relevance(mock_article, keywords)

        # Should have zero or very low score
        assert score == 0.0

    def test_calculate_relevance_seo_keywords_match(self):
        """Test relevance calculation with SEO keywords match."""
        service = LinkService()

        mock_article = Mock()
        mock_article.title = "業務効率化の方法"
        mock_article.seo_keywords = "予算管理, Excel, 効率化"
        mock_article.draft_content_md = "効率化について..."

        keywords = ["予算管理", "Excel"]
        score = service._calculate_relevance(mock_article, keywords)

        # Should have medium score due to SEO keyword match
        assert score > 0.3

    def test_link_suggestion_result_empty(self):
        """Test empty LinkSuggestionResult."""
        result = LinkSuggestionResult()

        assert result.suggestions == []
        assert result.source_keywords == []
        assert result.error_message == ""

        d = result.to_dict()
        assert d["suggestions"] == []


class TestLinkSuggestionIntegration:
    """Integration tests for link suggestion (require mocking)."""

    @patch("src.services.link_service.get_session")
    def test_full_suggestion_flow(self, mock_get_session):
        """Test full link suggestion workflow."""
        from src.database.models import ArticleStatus

        # Create mock articles
        mock_article1 = Mock()
        mock_article1.id = "article-1"
        mock_article1.title = "予算管理入門"
        mock_article1.seo_keywords = "予算管理, 入門, FP&A"
        mock_article1.draft_content_md = "予算管理の基本を解説..."
        mock_article1.published_url = "https://note.com/article1"
        mock_article1.status = ArticleStatus.COMPLETED

        mock_article2 = Mock()
        mock_article2.id = "article-2"
        mock_article2.title = "Excel脱却ガイド"
        mock_article2.seo_keywords = "Excel, 脱却, ツール"
        mock_article2.draft_content_md = "Excelからの移行..."
        mock_article2.published_url = None
        mock_article2.status = ArticleStatus.REVIEW

        mock_session = MagicMock()
        mock_repo = Mock()
        mock_repo.get_all.return_value = [mock_article1, mock_article2]
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_get_session.return_value = mock_session

        with patch("src.services.link_service.ArticleRepository", return_value=mock_repo):
            service = LinkService()
            result = service.suggest_internal_links(
                """## 予算管理の課題

多くの企業では**予算管理**に課題を抱えています。
Excelでの管理には限界があります。
""",
                exclude_article_id="current-article",
            )

            assert isinstance(result, LinkSuggestionResult)
            # Should find at least one related article
            assert len(result.suggestions) >= 1

            # First suggestion should be about 予算管理 (higher relevance)
            if result.suggestions:
                assert "予算" in result.suggestions[0].title or "Excel" in result.suggestions[0].title
