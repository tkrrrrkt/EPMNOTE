"""
EPM Note Engine - Theme Proposal Agent

Proposes article themes by combining SEO trend analysis (Tavily) and
knowledge base content (RAG) to generate high-quality topic suggestions.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    get_anthropic_client,
    get_settings,
    get_tavily_client,
    resolve_tavily_domains,
)
from src.repositories.rag_service import RAGService

logger = logging.getLogger(__name__)


# ===========================================
# Data Classes
# ===========================================


@dataclass
class ThemeProposalInput:
    """Input for theme proposal request."""

    axis_keyword: str  # Core keyword (e.g., "予算管理")
    persona: str  # Target persona (e.g., "CFO、経営企画部長")
    num_proposals: int = 7  # Number of proposals (5-10)
    tavily_profile: str | None = None  # Tavily domain profile


@dataclass
class ProposedTheme:
    """A single proposed article theme."""

    title: str  # Proposed article title
    seo_keywords: list[str] = field(default_factory=list)  # SEO keywords
    persona: str = ""  # Target persona for this theme
    summary: str = ""  # Brief summary (100-200 chars)
    source_type: str = "hybrid"  # "seo_trend", "knowledge_base", "hybrid"
    relevance_score: float = 0.0  # Relevance score (0-1)
    competitor_insights: list[str] = field(default_factory=list)  # Competitor insights


@dataclass
class ThemeProposalResult:
    """Complete theme proposal result."""

    input_keyword: str
    input_persona: str
    proposals: list[ProposedTheme] = field(default_factory=list)
    seo_trends: list[str] = field(default_factory=list)  # Trends from Tavily
    knowledge_topics: list[str] = field(default_factory=list)  # Topics from RAG
    generation_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/display."""
        return {
            "input_keyword": self.input_keyword,
            "input_persona": self.input_persona,
            "proposals": [
                {
                    "title": p.title,
                    "seo_keywords": p.seo_keywords,
                    "persona": p.persona,
                    "summary": p.summary,
                    "source_type": p.source_type,
                    "relevance_score": p.relevance_score,
                    "competitor_insights": p.competitor_insights,
                }
                for p in self.proposals
            ],
            "seo_trends": self.seo_trends,
            "knowledge_topics": self.knowledge_topics,
            "generation_summary": self.generation_summary,
        }


# ===========================================
# Theme Proposal Agent
# ===========================================


class ThemeProposalAgent:
    """
    Article theme proposal agent.

    Combines Tavily search (SEO trends) and RAG (knowledge base) with GPT-4o
    to generate optimized article theme proposals.
    """

    def __init__(self, rag_service: RAGService | None = None) -> None:
        """Initialize the agent with optional RAG service."""
        self.settings = get_settings()
        self.rag_service = rag_service

    def _get_rag_service(self) -> RAGService:
        """Get or create RAG service (lazy initialization)."""
        if self.rag_service is None:
            self.rag_service = RAGService()
        return self.rag_service

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def search_seo_trends(
        self,
        keyword: str,
        max_results: int = 10,
        domain_profile: str | None = None,
    ) -> tuple[list[dict], str]:
        """
        Search SEO trends using Tavily API.

        Args:
            keyword: Search keyword.
            max_results: Maximum number of results.
            domain_profile: Optional domain filter profile.

        Returns:
            Tuple of (search results, Tavily answer summary).
        """
        logger.info(f"Searching SEO trends for: {keyword}")

        client = get_tavily_client()
        if client is None:
            logger.warning("Tavily client not available")
            return [], ""

        # Construct search query
        query = f"{keyword} 記事 ブログ コンテンツ 経営管理 FP&A"

        # Resolve domain preferences (returns include, exclude, prefer)
        include_domains, exclude_domains, _ = resolve_tavily_domains(domain_profile)

        payload = {
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": True,
            "include_raw_content": False,
        }

        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        try:
            response = client.search(**payload)
            results = response.get("results", [])
            answer = response.get("answer", "")

            logger.info(f"Found {len(results)} SEO trend results")
            return results, answer

        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return [], ""

    def search_knowledge_base(
        self,
        keyword: str,
        top_k: int = 10,
    ) -> list[str]:
        """
        Search knowledge base using RAG.

        Args:
            keyword: Search keyword.
            top_k: Number of results to return.

        Returns:
            List of relevant content snippets.
        """
        logger.info(f"Searching knowledge base for: {keyword}")

        try:
            rag = self._get_rag_service()
            results = rag.search_knowledge_base(keyword, top_k=top_k)
            contents = [r.content for r in results]
            logger.info(f"Found {len(contents)} knowledge base results")
            return contents

        except Exception as e:
            logger.warning(f"Knowledge base search failed: {e}")
            return []

    def _format_seo_results(self, results: list[dict]) -> str:
        """Format SEO results for prompt."""
        if not results:
            return "(SEO検索結果なし)"

        lines = []
        for i, r in enumerate(results[:7], 1):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("content", "")[:200] if r.get("content") else ""
            lines.append(f"{i}. {title}\n   URL: {url}\n   概要: {snippet}")

        return "\n\n".join(lines)

    def _format_knowledge_contents(self, contents: list[str]) -> str:
        """Format knowledge base contents for prompt."""
        if not contents:
            return "(ナレッジベース検索結果なし)"

        formatted = []
        for i, content in enumerate(contents[:5], 1):
            truncated = content[:400] + "..." if len(content) > 400 else content
            formatted.append(f"【知見{i}】{truncated}")

        return "\n\n".join(formatted)

    def _extract_trends(self, results: list[dict]) -> list[str]:
        """Extract trend keywords from SEO results."""
        trends = []
        for r in results:
            title = r.get("title", "")
            if title:
                trends.append(title)
        return trends[:10]

    def _extract_topics(self, contents: list[str]) -> list[str]:
        """Extract topic summaries from knowledge base contents."""
        topics = []
        for content in contents[:5]:
            # Take first sentence or first 50 chars as topic
            first_sentence = content.split("。")[0] if "。" in content else content[:50]
            topics.append(first_sentence[:100])
        return topics

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def generate_proposals(
        self,
        input_data: ThemeProposalInput,
        seo_results: list[dict],
        seo_answer: str,
        knowledge_contents: list[str],
    ) -> ThemeProposalResult:
        """
        Generate theme proposals using Claude Sonnet.

        Args:
            input_data: Input configuration.
            seo_results: Tavily search results.
            seo_answer: Tavily answer summary.
            knowledge_contents: RAG knowledge base contents.

        Returns:
            ThemeProposalResult with generated proposals.
        """
        logger.info(f"Generating {input_data.num_proposals} theme proposals")

        client = get_anthropic_client()
        if client is None:
            logger.error("Anthropic client not available")
            return ThemeProposalResult(
                input_keyword=input_data.axis_keyword,
                input_persona=input_data.persona,
                generation_summary="Anthropic APIが利用できません",
            )

        seo_text = self._format_seo_results(seo_results)
        knowledge_text = self._format_knowledge_contents(knowledge_contents)

        prompt = f"""あなたはEPM・FP&A領域のコンテンツストラテジストです。
以下の情報を基に、{input_data.num_proposals}個の記事テーマを提案してください。

## 軸キーワード
{input_data.axis_keyword}

## ターゲットペルソナ
{input_data.persona}

## SEO競合記事（上位表示されている記事）
{seo_text}

## Tavilyサマリー
{seo_answer[:1500] if seo_answer else "(なし)"}

## ナレッジベース（社内知見・名著の示唆）
{knowledge_text}

## 出力形式（JSON形式で出力してください）
```json
{{
  "proposals": [
    {{
      "title": "魅力的な記事タイトル（30-50文字、数字や具体性を含める）",
      "seo_keywords": ["キーワード1", "キーワード2", "キーワード3"],
      "persona": "この記事のターゲット読者",
      "summary": "記事の概要（100-200文字）",
      "source_type": "hybrid",
      "competitor_insights": ["競合との差別化ポイント"]
    }}
  ]
}}
```

## 提案ガイドライン
1. **SEOで検索上位が狙えるテーマ**を優先（検索需要があるもの）
2. **競合と差別化できる**ナレッジベースの知見を活用
3. **ペルソナの課題・悩みに直結**するテーマを選定
4. タイトルは**30-50文字**、数字や具体性を含める
5. **既存の競合記事と被らない**オリジナルの切り口を提案
6. source_typeは以下から選択:
   - "seo_trend": SEO検索結果から着想
   - "knowledge_base": ナレッジベースの知見から着想
   - "hybrid": 両方を組み合わせた提案

JSON形式のみを出力してください。"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                system="あなたはEPM・FP&A領域のコンテンツマーケティング専門家です。JSON形式で回答してください。",
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.content[0].text if response.content else ""

            # Extract JSON from response
            json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try parsing the entire content as JSON
                json_str = content

            data = json.loads(json_str)
            proposals_data = data.get("proposals", [])

            proposals = []
            for p in proposals_data:
                proposals.append(
                    ProposedTheme(
                        title=p.get("title", ""),
                        seo_keywords=p.get("seo_keywords", []),
                        persona=p.get("persona", input_data.persona),
                        summary=p.get("summary", ""),
                        source_type=p.get("source_type", "hybrid"),
                        relevance_score=p.get("relevance_score", 0.7),
                        competitor_insights=p.get("competitor_insights", []),
                    )
                )

            logger.info(f"Generated {len(proposals)} theme proposals")

            return ThemeProposalResult(
                input_keyword=input_data.axis_keyword,
                input_persona=input_data.persona,
                proposals=proposals,
                seo_trends=self._extract_trends(seo_results),
                knowledge_topics=self._extract_topics(knowledge_contents),
                generation_summary=f"{len(proposals)}件のテーマを提案しました",
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return ThemeProposalResult(
                input_keyword=input_data.axis_keyword,
                input_persona=input_data.persona,
                generation_summary=f"JSON解析エラー: {e}",
            )

        except Exception as e:
            logger.error(f"Theme generation failed: {e}")
            return ThemeProposalResult(
                input_keyword=input_data.axis_keyword,
                input_persona=input_data.persona,
                generation_summary=f"生成エラー: {e}",
            )

    def propose(self, input_data: ThemeProposalInput) -> ThemeProposalResult:
        """
        Main entry point: propose article themes.

        Args:
            input_data: Theme proposal input configuration.

        Returns:
            ThemeProposalResult with generated proposals.
        """
        logger.info(f"Starting theme proposal for: {input_data.axis_keyword}")

        # Step 1: Search SEO trends
        seo_results, seo_answer = self.search_seo_trends(
            input_data.axis_keyword,
            max_results=10,
            domain_profile=input_data.tavily_profile,
        )

        # Step 2: Search knowledge base
        knowledge_contents = self.search_knowledge_base(input_data.axis_keyword)

        # Step 3: Generate proposals with GPT-4o
        result = self.generate_proposals(
            input_data,
            seo_results,
            seo_answer,
            knowledge_contents,
        )

        logger.info(f"Theme proposal completed: {len(result.proposals)} proposals")
        return result
