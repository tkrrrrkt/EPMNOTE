"""
Unit tests for EPM Note Engine agents.

Tests ResearchAgent, WriterAgent, and ReviewerAgent with mocked dependencies.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from src.agents.research_agent import (
    ResearchAgent,
    ResearchResult,
    CompetitorAnalysis,
)
from src.agents.writer_agent import WriterAgent, DraftResult
from src.agents.reviewer_agent import ReviewerAgent, ReviewResult, ScoreBreakdown


# ============================================================================
# ResearchAgent Tests
# ============================================================================

class TestResearchAgent:
    """Tests for ResearchAgent."""

    @pytest.fixture
    def mock_rag_service(self):
        """Create a mock RAG service."""
        mock = Mock()
        mock.search_knowledge_base.return_value = [
            Mock(content="内部ナレッジ1: 予算管理のベストプラクティス"),
            Mock(content="内部ナレッジ2: FP&Aの役割と責任"),
        ]
        return mock

    @pytest.fixture
    def mock_tavily_response(self):
        """Create a mock Tavily search response."""
        return {
            "results": [
                {
                    "url": "https://example.com/article1",
                    "title": "予実管理の基本",
                    "content": "## 予実管理とは\n予実管理は経営において重要な...",
                },
                {
                    "url": "https://example.com/article2",
                    "title": "FP&A入門ガイド",
                    "content": "## FP&Aの役割\n財務計画と分析を担当する...",
                },
            ]
        }

    def test_extract_headings_markdown(self):
        """Test heading extraction from Markdown content."""
        agent = ResearchAgent.__new__(ResearchAgent)

        content = """# 大見出し
## 中見出し1
テキスト
### 小見出し
## 中見出し2
"""
        headings = agent.extract_headings(content)

        assert "大見出し" in headings
        assert "中見出し1" in headings
        assert "小見出し" in headings
        assert "中見出し2" in headings

    def test_extract_headings_japanese_brackets(self):
        """Test heading extraction with Japanese bracket format."""
        agent = ResearchAgent.__new__(ResearchAgent)

        content = """【はじめに】
内容
【本論】
内容
"""
        headings = agent.extract_headings(content)

        assert "はじめに" in headings
        assert "本論" in headings

    def test_extract_headings_numbered(self):
        """Test heading extraction from numbered lists."""
        agent = ResearchAgent.__new__(ResearchAgent)

        content = """1. 第一章
2. 第二章
3. 第三章
"""
        headings = agent.extract_headings(content)

        assert "第一章" in headings
        assert "第二章" in headings
        assert "第三章" in headings

    @patch("src.agents.research_agent.resolve_tavily_domains")
    @patch("src.agents.research_agent.get_tavily_client")
    @patch("src.agents.research_agent.get_settings")
    def test_search_competitors(
        self, mock_settings, mock_tavily, mock_resolve_domains, mock_rag_service, mock_tavily_response
    ):
        """Test competitor search with Tavily API."""
        mock_tavily_client = Mock()
        mock_tavily_client.search.return_value = mock_tavily_response
        mock_tavily.return_value = mock_tavily_client
        mock_settings.return_value = Mock()
        # Mock resolve_tavily_domains to return empty domain lists (no filtering)
        mock_resolve_domains.return_value = ([], [], [])

        agent = ResearchAgent(rag_service=mock_rag_service)
        response = agent.search_competitors("予算管理")

        # search_competitors returns the full Tavily response dict
        assert "results" in response
        assert len(response["results"]) == 2
        assert response["results"][0]["url"] == "https://example.com/article1"
        mock_tavily_client.search.assert_called_once()

    @patch("src.agents.research_agent.get_openai_client")
    @patch("src.agents.research_agent.get_settings")
    def test_analyze_content_gaps(self, mock_settings, mock_openai, mock_rag_service):
        """Test content gap analysis."""
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content="- 差別化ポイント1: 実践的なテンプレートの提供\n- 差別化ポイント2: 日本企業向けのカスタマイズ"
                )
            )
        ]
        mock_openai_client = Mock()
        mock_openai_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_openai_client
        mock_settings.return_value = Mock()

        agent = ResearchAgent(rag_service=mock_rag_service)
        gaps = agent.analyze_content_gaps(
            competitor_content=["競合コンテンツ1"],
            internal_knowledge=["内部ナレッジ1"],
        )

        assert len(gaps) == 2
        assert "差別化ポイント1" in gaps[0]

    def test_search_internal_knowledge(self, mock_rag_service):
        """Test internal knowledge search."""
        with patch("src.agents.research_agent.get_settings"):
            agent = ResearchAgent(rag_service=mock_rag_service)
            results = agent.search_internal_knowledge("予算管理")

            assert len(results) == 2
            assert "内部ナレッジ1" in results[0]


# ============================================================================
# WriterAgent Tests
# ============================================================================

class TestWriterAgent:
    """Tests for WriterAgent."""

    @pytest.fixture
    def mock_research_result(self):
        """Create a mock research result."""
        return ResearchResult(
            competitor_analysis=CompetitorAnalysis(
                urls=["https://example.com/1"],
                headings=[["見出し1", "見出し2"]],
                content_gaps=["差別化ポイント1"],
                key_points=["キーポイント1"],
            ),
            internal_references=["内部参照1"],
            suggested_outline=["導入", "本論", "まとめ"],
            research_summary="リサーチサマリー",
        )

    @patch("src.agents.writer_agent.get_anthropic_client")
    def test_generate_draft(self, mock_anthropic, mock_research_result):
        """Test draft generation."""
        mock_response = Mock()
        mock_response.content = [
            Mock(text="# テスト記事\n\n## 導入\n\nこれはテスト記事です。")
        ]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        agent = WriterAgent()
        result = agent.generate_draft(
            research_result=mock_research_result,
            essences=[{"category": "体験談", "content": "私の経験"}],
            target_persona="経営企画部長",
            article_title="予算管理入門",
        )

        assert isinstance(result, DraftResult)
        assert "テスト記事" in result.draft_content_md
        assert mock_client.messages.create.call_count >= 1

    @patch("src.agents.writer_agent.get_anthropic_client")
    def test_generate_titles(self, mock_anthropic):
        """Test title generation."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text="1. 【完全ガイド】予算管理の始め方\n2. 予算管理で業績アップ！実践ノウハウ"
            )
        ]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        agent = WriterAgent()
        titles = agent._generate_titles(
            base_title="予算管理入門",
            target_persona="経営企画部長",
            content_preview="予算管理は重要です...",
        )

        assert len(titles) >= 1
        assert "予算管理" in titles[0]

    @patch("src.agents.writer_agent.get_anthropic_client")
    def test_revise_draft(self, mock_anthropic):
        """Test draft revision."""
        mock_response = Mock()
        mock_response.content = [Mock(text="# 改善後の記事\n\n改善されたコンテンツ")]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        agent = WriterAgent()
        revised = agent.revise_draft(
            original_content="# 元の記事",
            feedback="ターゲット訴求力を強化してください",
            score_breakdown={"target_appeal": 20, "logical_structure": 30, "seo_fitness": 20},
        )

        assert "改善後" in revised


# ============================================================================
# ReviewerAgent Tests
# ============================================================================

class TestReviewerAgent:
    """Tests for ReviewerAgent."""

    @patch("src.agents.reviewer_agent.get_anthropic_client")
    def test_review_passing_score(self, mock_anthropic):
        """Test review with passing score."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text="""```json
{
  "target_appeal": {"score": 28, "evaluation": "良好", "improvements": []},
  "logical_structure": {"score": 35, "evaluation": "良好", "improvements": []},
  "seo_fitness": {"score": 25, "evaluation": "良好", "improvements": []},
  "overall_feedback": "全体的に良い記事です",
  "strengths": ["読みやすい"],
  "priority_improvements": []
}
```"""
            )
        ]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        agent = ReviewerAgent()
        result = agent.review(
            draft_content="# テスト記事\n\nコンテンツ",
            target_persona="経営企画部長",
            seo_keywords="予算管理",
        )

        assert isinstance(result, ReviewResult)
        assert result.score == 88  # 28 + 35 + 25
        assert result.passed is True
        assert result.breakdown.target_appeal == 28

    @patch("src.agents.reviewer_agent.get_anthropic_client")
    def test_review_failing_score(self, mock_anthropic):
        """Test review with failing score."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text="""```json
{
  "target_appeal": {"score": 15, "evaluation": "改善が必要", "improvements": ["ペルソナへの訴求が弱い"]},
  "logical_structure": {"score": 25, "evaluation": "改善が必要", "improvements": ["構成が不明確"]},
  "seo_fitness": {"score": 15, "evaluation": "改善が必要", "improvements": ["キーワードが少ない"]},
  "overall_feedback": "改善が必要です",
  "strengths": [],
  "priority_improvements": ["ターゲット訴求を強化"]
}
```"""
            )
        ]
        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        agent = ReviewerAgent()
        result = agent.review(
            draft_content="# 記事",
            target_persona="経営企画部長",
            seo_keywords="予算管理",
        )

        assert result.score == 55  # 15 + 25 + 15
        assert result.passed is False

    def test_quick_check_short_content(self):
        """Test quick check with short content."""
        with patch("src.agents.reviewer_agent.get_anthropic_client"):
            agent = ReviewerAgent()
            result = agent.quick_check("短いコンテンツ")

            assert result["word_count"] < 2500
            assert not result["quick_pass"]
            assert len(result["issues"]) > 0

    def test_quick_check_good_content(self):
        """Test quick check with good content including structure elements."""
        with patch("src.agents.reviewer_agent.get_anthropic_client"):
            agent = ReviewerAgent()

            # Create content that passes all checks including 11 mandatory structure elements
            # The quick_pass condition requires: len(issues) == 0 and len(missing_elements) <= 2
            content = """「予算と実績が合わないんですけど、どうすればいいですか？」

**結論から言います。** 予実管理の基本は3つのステップです。

## 目次
1. はじめに
2. 原因分析
3. 解決策

## 一枚絵
┌─────────────────┐
│  予実管理の全体像   │
└─────────────────┘

## 原因①：データ収集の問題
原因②：分析手法の未整備
原因③：組織体制の課題

## ロードマップ
Week 1: 現状分析
Week 2: 改善策の策定

## アンチパターン
失敗①：ツール先行の導入
失敗②：現場を巻き込まない

## 情シスの方へ
DXの方へ：システム連携のポイント

## 今日の持ち帰りチェックリスト
- [ ] 現状の課題を整理する
- [ ] 関係者と共有する

## 次に読む
関連記事：予算管理の実践ガイド

## お問い合わせ
プロフィールのリンクからお気軽にどうぞ
""" + "A" * 2500  # Add padding to reach word count threshold

            result = agent.quick_check(content)

            assert result["word_count"] >= 2500
            assert result["heading_count"] >= 5
            assert result["has_action_item"] is True
            assert result["structure_found"] >= 9  # At least 9 of 11 elements
            assert result["quick_pass"] is True


# ============================================================================
# ScoreBreakdown Tests
# ============================================================================

class TestScoreBreakdown:
    """Tests for ScoreBreakdown dataclass."""

    def test_default_values(self):
        """Test default score values."""
        breakdown = ScoreBreakdown()

        assert breakdown.target_appeal == 0
        assert breakdown.logical_structure == 0
        assert breakdown.seo_fitness == 0

    def test_custom_values(self):
        """Test custom score values."""
        breakdown = ScoreBreakdown(
            target_appeal=25,
            logical_structure=35,
            seo_fitness=20,
        )

        total = breakdown.target_appeal + breakdown.logical_structure + breakdown.seo_fitness
        assert total == 80


# ============================================================================
# ReviewResult Tests
# ============================================================================

class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_passed_threshold(self):
        """Test passing threshold is 80."""
        result_pass = ReviewResult(score=80)
        result_fail = ReviewResult(score=79)

        assert result_pass.passed is True
        assert result_fail.passed is False

    def test_post_init_sets_passed(self):
        """Test __post_init__ correctly sets passed based on score."""
        result = ReviewResult(score=85)
        assert result.passed is True

        result = ReviewResult(score=75)
        assert result.passed is False
