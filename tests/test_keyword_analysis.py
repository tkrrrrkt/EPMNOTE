"""
Unit tests for EPM Note Engine - SEO Keyword Analysis.

Tests KeywordAnalysis functionality in ResearchAgent.
"""

import pytest
from unittest.mock import Mock, patch

from src.agents.research_agent import (
    ResearchAgent,
    KeywordOccurrence,
    KeywordAnalysis,
    JANOME_AVAILABLE,
)


class TestKeywordOccurrence:
    """Tests for KeywordOccurrence dataclass."""

    def test_keyword_occurrence_defaults(self):
        """Test KeywordOccurrence with default values."""
        kw = KeywordOccurrence(keyword="予算管理", count=5, density=1.5)

        assert kw.keyword == "予算管理"
        assert kw.count == 5
        assert kw.density == 1.5
        assert kw.positions == []
        assert kw.in_first_paragraph is False
        assert kw.in_conclusion is False

    def test_keyword_occurrence_full(self):
        """Test KeywordOccurrence with all fields."""
        kw = KeywordOccurrence(
            keyword="経営管理",
            count=10,
            density=2.0,
            positions=["タイトル", "H2", "本文"],
            in_first_paragraph=True,
            in_conclusion=True,
        )

        assert kw.keyword == "経営管理"
        assert len(kw.positions) == 3
        assert kw.in_first_paragraph is True


class TestKeywordAnalysis:
    """Tests for KeywordAnalysis dataclass."""

    def test_keyword_analysis_defaults(self):
        """Test KeywordAnalysis with default values."""
        analysis = KeywordAnalysis()

        assert analysis.target_keywords == []
        assert analysis.total_words == 0
        assert analysis.primary_keyword is None
        assert analysis.related_keywords == []
        assert analysis.keyword_density_score == 0.0
        assert analysis.overall_seo_score == 0.0
        assert analysis.suggestions == []

    def test_keyword_analysis_full(self):
        """Test KeywordAnalysis with all fields."""
        primary = KeywordOccurrence(keyword="予算管理", count=5, density=1.5)
        related = [KeywordOccurrence(keyword="経営", count=3, density=0.8)]

        analysis = KeywordAnalysis(
            target_keywords=["予算管理", "経営"],
            total_words=1000,
            primary_keyword=primary,
            related_keywords=related,
            keyword_density_score=85.0,
            placement_score=70.0,
            overall_seo_score=77.5,
            suggestions=["タイトルにキーワードを追加"],
        )

        assert analysis.total_words == 1000
        assert analysis.primary_keyword.keyword == "予算管理"
        assert len(analysis.related_keywords) == 1
        assert analysis.overall_seo_score == 77.5

    def test_to_dict(self):
        """Test KeywordAnalysis to_dict conversion."""
        primary = KeywordOccurrence(
            keyword="テスト",
            count=3,
            density=1.0,
            positions=["H2"],
            in_first_paragraph=True,
            in_conclusion=False,
        )
        analysis = KeywordAnalysis(
            target_keywords=["テスト"],
            total_words=500,
            primary_keyword=primary,
            keyword_density_score=70.0,
            placement_score=60.0,
            overall_seo_score=65.0,
            suggestions=["提案1"],
        )

        result = analysis.to_dict()

        assert result["target_keywords"] == ["テスト"]
        assert result["total_words"] == 500
        assert result["primary_keyword"]["keyword"] == "テスト"
        assert result["primary_keyword"]["in_first_paragraph"] is True
        assert result["overall_seo_score"] == 65.0
        assert "提案1" in result["suggestions"]


class TestResearchAgentKeywordAnalysis:
    """Tests for ResearchAgent.analyze_keyword_density method."""

    @pytest.fixture
    def mock_rag_service(self):
        """Create a mock RAG service."""
        mock = Mock()
        mock.search_knowledge_base.return_value = []
        return mock

    @pytest.fixture
    def sample_article_content(self):
        """Create sample article content for testing."""
        return """# 予算管理の基本ガイド

## 目次
1. 予算管理とは
2. 予算管理の重要性
3. まとめ

予算管理は企業経営において非常に重要な要素です。
適切な予算管理を行うことで、企業の財務健全性を保つことができます。

## 予算管理とは

予算管理とは、企業の収支を計画し、実績と比較することで、
経営状況を把握・改善する活動です。

## 予算管理の重要性

予算管理が重要な理由は以下の3点です：
- 経営の可視化
- リソース配分の最適化
- 意思決定の迅速化

## まとめ

予算管理は経営の基盤です。今日から始めましょう。

---
お問い合わせはプロフィールのリンクからどうぞ。
"""

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_basic(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test basic keyword density analysis."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理"],
        )

        assert isinstance(result, KeywordAnalysis)
        assert result.target_keywords == ["予算管理"]
        assert result.total_words > 0
        assert result.primary_keyword is not None
        assert result.primary_keyword.keyword == "予算管理"
        assert result.primary_keyword.count >= 5  # 予算管理 appears multiple times

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_positions(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test keyword position detection."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理"],
        )

        primary = result.primary_keyword
        assert primary is not None
        # Should detect keyword in title (H1) or H2 - positions use English names
        assert "title" in primary.positions or "h2" in primary.positions
        # Should be in first paragraph
        assert primary.in_first_paragraph is True

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_multiple_keywords(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test analysis with multiple target keywords."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理", "経営", "企業"],
        )

        assert len(result.target_keywords) == 3
        # Primary should be the first one that appears
        assert result.primary_keyword is not None

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_score_calculation(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test SEO score calculation."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理"],
        )

        # Scores should be between 0 and 100
        assert 0 <= result.keyword_density_score <= 100
        assert 0 <= result.placement_score <= 100
        assert 0 <= result.overall_seo_score <= 100

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_suggestions(
        self, mock_settings, mock_rag_service
    ):
        """Test suggestion generation for poor content."""
        mock_settings.return_value = Mock()

        # Content with minimal keyword usage
        poor_content = """# タイトル

本文テキスト。

## 見出し

さらにテキスト。
"""

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=poor_content,
            target_keywords=["予算管理"],
        )

        # Should have suggestions for improvement
        assert len(result.suggestions) > 0

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_empty_content(
        self, mock_settings, mock_rag_service
    ):
        """Test analysis with empty content."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content="",
            target_keywords=["予算管理"],
        )

        assert result.total_words == 0
        # Primary keyword is still created but with count=0
        assert result.primary_keyword is not None
        assert result.primary_keyword.count == 0
        assert result.overall_seo_score == 0

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_no_keywords(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test analysis with empty keyword list."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=[],
        )

        assert result.primary_keyword is None
        assert result.overall_seo_score == 0

    @pytest.mark.skipif(not JANOME_AVAILABLE, reason="Janome not installed")
    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_with_janome(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test that Janome tokenization works correctly."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理"],
        )

        # With Janome, should extract related keywords
        # (This test verifies Janome integration when available)
        assert result.total_words > 0

    @patch("src.agents.research_agent.get_settings")
    def test_analyze_keyword_density_to_dict_integration(
        self, mock_settings, mock_rag_service, sample_article_content
    ):
        """Test that to_dict produces valid JSON-serializable output."""
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.analyze_keyword_density(
            content=sample_article_content,
            target_keywords=["予算管理"],
        )

        # Convert to dict (for JSONB storage)
        result_dict = result.to_dict()

        # Should be a valid dictionary
        assert isinstance(result_dict, dict)
        assert "target_keywords" in result_dict
        assert "overall_seo_score" in result_dict
        assert "suggestions" in result_dict

        # Should be JSON serializable
        import json
        json_str = json.dumps(result_dict, ensure_ascii=False)
        assert len(json_str) > 0


# ============================================================================
# Competitor Keyword Extraction Tests
# ============================================================================

from src.agents.research_agent import (
    CompetitorKeyword,
    CompetitorKeywordResult,
)


class TestCompetitorKeyword:
    """Tests for CompetitorKeyword dataclass."""

    def test_competitor_keyword_creation(self):
        """Test creating CompetitorKeyword with all fields."""
        kw = CompetitorKeyword(
            keyword="予算管理",
            article_count=7,
            total_articles=10,
            usage_rate=70.0,
            found_in_titles=5,
            found_in_headings=3,
            priority="必須",
        )

        assert kw.keyword == "予算管理"
        assert kw.article_count == 7
        assert kw.usage_rate == 70.0
        assert kw.priority == "必須"


class TestCompetitorKeywordResult:
    """Tests for CompetitorKeywordResult dataclass."""

    def test_competitor_keyword_result_defaults(self):
        """Test CompetitorKeywordResult with default values."""
        result = CompetitorKeywordResult(query="予算管理")

        assert result.query == "予算管理"
        assert result.total_articles == 0
        assert result.keywords == []
        assert result.suggestions == []

    def test_to_dict(self):
        """Test converting CompetitorKeywordResult to dictionary."""
        kw = CompetitorKeyword(
            keyword="PDCA",
            article_count=5,
            total_articles=10,
            usage_rate=50.0,
            found_in_titles=2,
            found_in_headings=4,
            priority="推奨",
        )
        result = CompetitorKeywordResult(
            query="予算管理",
            total_articles=10,
            keywords=[kw],
            article_titles=["記事1", "記事2"],
            article_urls=["https://example.com/1", "https://example.com/2"],
            suggestions=["推奨アクション1"],
        )

        d = result.to_dict()

        assert d["query"] == "予算管理"
        assert d["total_articles"] == 10
        assert len(d["keywords"]) == 1
        assert d["keywords"][0]["keyword"] == "PDCA"
        assert d["keywords"][0]["priority"] == "推奨"
        assert len(d["article_titles"]) == 2


class TestResearchAgentCompetitorKeywords:
    """Tests for ResearchAgent.extract_competitor_keywords method."""

    @pytest.fixture
    def mock_rag_service(self):
        """Create a mock RAG service."""
        mock = Mock()
        mock.search_knowledge_base.return_value = []
        return mock

    @pytest.fixture
    def mock_tavily_response(self):
        """Create a mock Tavily search response for competitor analysis."""
        return {
            "results": [
                {
                    "url": "https://example.com/article1",
                    "title": "【完全ガイド】予算管理の基本とPDCAサイクル",
                    "content": "## 予算管理とは\n予算管理は経営において重要...\n## PDCAサイクルの活用\n計画と実績を比較...",
                },
                {
                    "url": "https://example.com/article2",
                    "title": "予算管理の始め方｜Excelテンプレート付き",
                    "content": "## 予算管理のポイント\n初心者向けガイド...\n## Excelで始める予算管理\nテンプレート...",
                },
                {
                    "url": "https://example.com/article3",
                    "title": "経営企画が教える予算管理のコツ",
                    "content": "## 予算管理の重要性\n経営の基盤として...\n## 失敗しないポイント\n注意すべき点...",
                },
            ]
        }

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_basic(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service, mock_tavily_response
    ):
        """Test basic competitor keyword extraction."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("予算管理", max_articles=10)

        assert isinstance(result, CompetitorKeywordResult)
        assert result.query == "予算管理"
        assert result.total_articles == 3
        assert len(result.article_titles) == 3
        assert len(result.article_urls) == 3

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_finds_common_keywords(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service, mock_tavily_response
    ):
        """Test that common keywords are extracted from competitor articles."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("予算管理", max_articles=10)

        # Should have extracted some keywords
        assert len(result.keywords) > 0

        # Keywords should have proper structure
        for kw in result.keywords:
            assert kw.keyword
            assert kw.total_articles == 3
            assert kw.usage_rate >= 0
            assert kw.priority in ["必須", "推奨", "検討"]

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_priority_assignment(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service, mock_tavily_response
    ):
        """Test that priority is correctly assigned based on usage rate."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("予算管理", max_articles=10)

        # Check priority assignment logic
        for kw in result.keywords:
            if kw.usage_rate >= 70:
                assert kw.priority == "必須"
            elif kw.usage_rate >= 40:
                assert kw.priority == "推奨"
            else:
                assert kw.priority == "検討"

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_generates_suggestions(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service, mock_tavily_response
    ):
        """Test that suggestions are generated."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("予算管理", max_articles=10)

        # Should have some suggestions
        assert len(result.suggestions) > 0

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_empty_results(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service
    ):
        """Test handling of empty search results."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = {"results": []}
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("非常にレアなキーワード")

        assert result.total_articles == 0
        assert len(result.keywords) == 0
        assert "見つかりませんでした" in result.suggestions[0]

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_extract_competitor_keywords_to_dict(
        self, mock_settings, mock_tavily, mock_resolve_domains,
        mock_rag_service, mock_tavily_response
    ):
        """Test that to_dict produces valid JSON-serializable output."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        result = agent.extract_competitor_keywords("予算管理", max_articles=10)

        # Convert to dict
        result_dict = result.to_dict()

        # Should be valid dictionary
        assert isinstance(result_dict, dict)
        assert "query" in result_dict
        assert "keywords" in result_dict
        assert "suggestions" in result_dict

        # Should be JSON serializable
        import json
        json_str = json.dumps(result_dict, ensure_ascii=False)
        assert len(json_str) > 0
