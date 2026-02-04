"""
Unit tests for ThemeProposalAgent.

Tests theme proposal generation with mocked Tavily and RAG dependencies.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.agents.theme_proposal_agent import (
    ThemeProposalAgent,
    ThemeProposalInput,
    ThemeProposalResult,
    ProposedTheme,
)


class TestThemeProposalAgent:
    """Tests for ThemeProposalAgent."""

    @pytest.fixture
    def mock_rag_service(self):
        """Create a mock RAG service."""
        mock = Mock()
        mock.search_knowledge_base.return_value = [
            Mock(content="内部ナレッジ1: 予算管理のベストプラクティス。計画と実績の乖離を分析することが重要。"),
            Mock(content="内部ナレッジ2: FP&Aの役割と責任。経営陣への提言が求められる。"),
            Mock(content="内部ナレッジ3: KPI設計のポイント。測定可能な指標を選ぶ。"),
        ]
        return mock

    @pytest.fixture
    def mock_tavily_response(self):
        """Create a mock Tavily search response."""
        return {
            "results": [
                {
                    "url": "https://example.com/article1",
                    "title": "予実管理の基本と実践",
                    "content": "予実管理は経営において重要な管理会計手法です。",
                },
                {
                    "url": "https://example.com/article2",
                    "title": "FP&A入門ガイド",
                    "content": "財務計画と分析を担当するFP&A部門の役割について解説。",
                },
                {
                    "url": "https://example.com/article3",
                    "title": "Excel脱却の5ステップ",
                    "content": "Excelでの予算管理から専用ツールへの移行方法。",
                },
            ],
            "answer": "予算管理はExcelから専用ツールへ移行する企業が増加傾向にあります。",
        }

    @pytest.fixture
    def mock_anthropic_response(self):
        """Create a mock Claude Sonnet response."""
        return MagicMock(
            content=[
                MagicMock(
                    text="""```json
{
  "proposals": [
    {
      "title": "予実管理「数字が合わない」問題の正体と3つの解決策",
      "seo_keywords": ["予実管理", "数字が合わない", "解決策"],
      "persona": "CFO、経営企画部長",
      "summary": "予実の数字が合わない問題は、多くの企業で発生しています。本記事では根本原因と具体的な解決策を解説します。",
      "source_type": "hybrid",
      "competitor_insights": ["競合はExcel移行に焦点", "根本原因の解説が少ない"]
    },
    {
      "title": "FP&A担当者が知るべき予算策定の落とし穴5選",
      "seo_keywords": ["FP&A", "予算策定", "落とし穴"],
      "persona": "FP&A担当者、経営企画部",
      "summary": "予算策定時によくある失敗パターンと、それを回避するための具体的なアプローチを紹介します。",
      "source_type": "knowledge_base",
      "competitor_insights": ["ベストプラクティスの具体例が少ない"]
    }
  ]
}
```"""
                )
            ]
        )

    def test_dataclass_creation(self):
        """Test ThemeProposalInput and ProposedTheme dataclass creation."""
        input_data = ThemeProposalInput(
            axis_keyword="予算管理",
            persona="CFO",
            num_proposals=5,
        )
        assert input_data.axis_keyword == "予算管理"
        assert input_data.persona == "CFO"
        assert input_data.num_proposals == 5

        theme = ProposedTheme(
            title="テストタイトル",
            seo_keywords=["キーワード1", "キーワード2"],
            persona="テストペルソナ",
            summary="テスト概要",
            source_type="hybrid",
        )
        assert theme.title == "テストタイトル"
        assert len(theme.seo_keywords) == 2
        assert theme.source_type == "hybrid"

    def test_result_to_dict(self):
        """Test ThemeProposalResult.to_dict() method."""
        result = ThemeProposalResult(
            input_keyword="予算管理",
            input_persona="CFO",
            proposals=[
                ProposedTheme(
                    title="テストタイトル",
                    seo_keywords=["KW1", "KW2"],
                    persona="CFO",
                    summary="概要",
                    source_type="hybrid",
                )
            ],
            seo_trends=["トレンド1", "トレンド2"],
            knowledge_topics=["トピック1"],
            generation_summary="1件生成",
        )

        d = result.to_dict()
        assert d["input_keyword"] == "予算管理"
        assert len(d["proposals"]) == 1
        assert d["proposals"][0]["title"] == "テストタイトル"
        assert len(d["seo_trends"]) == 2

    @patch("src.agents.theme_proposal_agent.get_tavily_client")
    def test_search_seo_trends_success(self, mock_get_client, mock_tavily_response):
        """Test successful SEO trends search."""
        mock_client = Mock()
        mock_client.search.return_value = mock_tavily_response
        mock_get_client.return_value = mock_client

        agent = ThemeProposalAgent()
        results, answer = agent.search_seo_trends("予算管理")

        assert len(results) == 3
        assert results[0]["title"] == "予実管理の基本と実践"
        assert "予算管理" in answer

    @patch("src.agents.theme_proposal_agent.get_tavily_client")
    def test_search_seo_trends_no_client(self, mock_get_client):
        """Test SEO trends search when Tavily client is not available."""
        mock_get_client.return_value = None

        agent = ThemeProposalAgent()
        results, answer = agent.search_seo_trends("予算管理")

        assert results == []
        assert answer == ""

    def test_search_knowledge_base_success(self, mock_rag_service):
        """Test successful knowledge base search."""
        agent = ThemeProposalAgent(rag_service=mock_rag_service)
        contents = agent.search_knowledge_base("予算管理")

        assert len(contents) == 3
        assert "ベストプラクティス" in contents[0]

    def test_search_knowledge_base_empty(self):
        """Test knowledge base search with no results."""
        mock_rag = Mock()
        mock_rag.search_knowledge_base.return_value = []

        agent = ThemeProposalAgent(rag_service=mock_rag)
        contents = agent.search_knowledge_base("存在しないキーワード")

        assert contents == []

    def test_format_seo_results(self):
        """Test SEO results formatting for prompt."""
        agent = ThemeProposalAgent()

        results = [
            {"title": "タイトル1", "url": "https://example.com/1", "content": "内容1"},
            {"title": "タイトル2", "url": "https://example.com/2", "content": "内容2"},
        ]

        formatted = agent._format_seo_results(results)
        assert "タイトル1" in formatted
        assert "https://example.com/1" in formatted
        assert "内容1" in formatted

    def test_format_seo_results_empty(self):
        """Test SEO results formatting with empty results."""
        agent = ThemeProposalAgent()
        formatted = agent._format_seo_results([])
        assert "なし" in formatted

    def test_format_knowledge_contents(self):
        """Test knowledge contents formatting for prompt."""
        agent = ThemeProposalAgent()

        contents = [
            "ナレッジ1の内容です。これは長いテキストです。" * 20,
            "ナレッジ2の内容です。",
        ]

        formatted = agent._format_knowledge_contents(contents)
        assert "【知見1】" in formatted
        assert "【知見2】" in formatted
        # Long content should be truncated
        assert "..." in formatted

    def test_format_knowledge_contents_empty(self):
        """Test knowledge contents formatting with empty contents."""
        agent = ThemeProposalAgent()
        formatted = agent._format_knowledge_contents([])
        assert "なし" in formatted

    def test_extract_trends(self):
        """Test trend extraction from SEO results."""
        agent = ThemeProposalAgent()

        results = [
            {"title": "トレンド記事1"},
            {"title": "トレンド記事2"},
            {"title": "トレンド記事3"},
        ]

        trends = agent._extract_trends(results)
        assert len(trends) == 3
        assert "トレンド記事1" in trends

    def test_extract_topics(self):
        """Test topic extraction from knowledge contents."""
        agent = ThemeProposalAgent()

        contents = [
            "これはトピック1です。詳細な説明が続きます。",
            "トピック2について。ここにも説明があります。",
        ]

        topics = agent._extract_topics(contents)
        assert len(topics) == 2
        assert "トピック1" in topics[0]

    @patch("src.agents.theme_proposal_agent.get_anthropic_client")
    def test_generate_proposals_success(self, mock_get_client, mock_anthropic_response):
        """Test successful theme proposal generation."""
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_anthropic_response
        mock_get_client.return_value = mock_client

        agent = ThemeProposalAgent()
        input_data = ThemeProposalInput(
            axis_keyword="予算管理",
            persona="CFO",
            num_proposals=5,
        )

        result = agent.generate_proposals(
            input_data,
            seo_results=[{"title": "SEO記事", "url": "https://example.com", "content": "内容"}],
            seo_answer="SEOサマリー",
            knowledge_contents=["ナレッジ1", "ナレッジ2"],
        )

        assert len(result.proposals) == 2
        assert "予実管理" in result.proposals[0].title
        assert result.proposals[0].source_type == "hybrid"

    @patch("src.agents.theme_proposal_agent.get_anthropic_client")
    def test_generate_proposals_no_client(self, mock_get_client):
        """Test proposal generation when Anthropic client is not available."""
        mock_get_client.return_value = None

        agent = ThemeProposalAgent()
        input_data = ThemeProposalInput(
            axis_keyword="予算管理",
            persona="CFO",
        )

        result = agent.generate_proposals(input_data, [], "", [])

        assert len(result.proposals) == 0
        assert "利用できません" in result.generation_summary

    @patch("src.agents.theme_proposal_agent.get_anthropic_client")
    @patch("src.agents.theme_proposal_agent.get_tavily_client")
    def test_propose_full_flow(
        self,
        mock_get_tavily,
        mock_get_anthropic,
        mock_rag_service,
        mock_tavily_response,
        mock_anthropic_response,
    ):
        """Test full proposal flow with all components."""
        # Setup mocks
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_get_tavily.return_value = mock_tavily_client

        mock_anthropic_client = Mock()
        mock_anthropic_client.messages.create.return_value = mock_anthropic_response
        mock_get_anthropic.return_value = mock_anthropic_client

        # Create agent and run propose
        agent = ThemeProposalAgent(rag_service=mock_rag_service)
        input_data = ThemeProposalInput(
            axis_keyword="予算管理",
            persona="CFO",
            num_proposals=5,
        )

        result = agent.propose(input_data)

        # Verify result
        assert isinstance(result, ThemeProposalResult)
        assert result.input_keyword == "予算管理"
        assert len(result.proposals) == 2
        assert len(result.seo_trends) > 0
        assert len(result.knowledge_topics) > 0

    def test_propose_with_tavily_profile(self, mock_rag_service):
        """Test proposal with tavily_profile parameter."""
        input_data = ThemeProposalInput(
            axis_keyword="予算管理",
            persona="CFO",
            num_proposals=5,
            tavily_profile="evidence",
        )

        assert input_data.tavily_profile == "evidence"


class TestProposedTheme:
    """Tests for ProposedTheme dataclass."""

    def test_default_values(self):
        """Test ProposedTheme default values."""
        theme = ProposedTheme(title="テスト")

        assert theme.title == "テスト"
        assert theme.seo_keywords == []
        assert theme.persona == ""
        assert theme.summary == ""
        assert theme.source_type == "hybrid"
        assert theme.relevance_score == 0.0
        assert theme.competitor_insights == []

    def test_all_values(self):
        """Test ProposedTheme with all values."""
        theme = ProposedTheme(
            title="完全なテーマ",
            seo_keywords=["KW1", "KW2", "KW3"],
            persona="詳細なペルソナ",
            summary="詳細な概要",
            source_type="seo_trend",
            relevance_score=0.95,
            competitor_insights=["競合分析1", "競合分析2"],
        )

        assert theme.title == "完全なテーマ"
        assert len(theme.seo_keywords) == 3
        assert theme.source_type == "seo_trend"
        assert theme.relevance_score == 0.95


class TestThemeProposalResult:
    """Tests for ThemeProposalResult dataclass."""

    def test_empty_result(self):
        """Test empty ThemeProposalResult."""
        result = ThemeProposalResult(
            input_keyword="テスト",
            input_persona="ペルソナ",
        )

        assert result.input_keyword == "テスト"
        assert result.proposals == []
        assert result.seo_trends == []
        assert result.knowledge_topics == []
        assert result.generation_summary == ""

    def test_to_dict_empty(self):
        """Test to_dict with empty result."""
        result = ThemeProposalResult(
            input_keyword="テスト",
            input_persona="ペルソナ",
        )

        d = result.to_dict()
        assert d["proposals"] == []
        assert d["seo_trends"] == []
