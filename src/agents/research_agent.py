"""
EPM Note Engine - Research Agent

Performs SEO competitor analysis using Tavily API and internal knowledge search.
"""

import logging
from dataclasses import dataclass, field

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    get_openai_client,
    get_settings,
    get_tavily_client,
    resolve_tavily_domains,
)
from src.repositories.rag_service import RAGService

logger = logging.getLogger(__name__)


@dataclass
class CompetitorAnalysis:
    """Analysis results from competitor research."""

    urls: list[str] = field(default_factory=list)
    headings: list[list[str]] = field(default_factory=list)
    content_gaps: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)


@dataclass
class ResearchResult:
    """Complete research results."""

    competitor_analysis: CompetitorAnalysis
    internal_references: list[str] = field(default_factory=list)
    suggested_outline: list[str] = field(default_factory=list)
    research_summary: str = ""
    tavily_answer: str = ""


class ResearchAgent:
    """
    Agent for SEO research and competitor analysis.

    Uses Tavily API for web search and ChromaDB for internal knowledge.
    """

    def __init__(self, rag_service: RAGService | None = None) -> None:
        """
        Initialize the research agent.

        Args:
            rag_service: Optional RAG service for internal knowledge search.
        """
        self.settings = get_settings()
        self.rag_service = rag_service or RAGService()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def search_competitors(
        self,
        seo_keywords: str,
        max_results: int = 5,
        domain_profile: str | None = None,
    ) -> dict:
        """
        Search for competitor articles using Tavily API.

        Args:
            seo_keywords: SEO keywords to search for.
            max_results: Maximum number of results to return.

        Returns:
            Tavily response dict including results and (optional) answer.
        """
        try:
            client = get_tavily_client()

            # Build search query
            query = f"{seo_keywords} 経営管理 FP&A 予実管理"
            payload = {
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
                "include_raw_content": False,
            }

            include_domains, exclude_domains, prefer_domains = resolve_tavily_domains(
                domain_profile,
                self.settings,
            )

            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            try:
                response = client.search(**payload)
            except TypeError as e:
                # Fallback for older client versions without domain filters
                logger.warning(f"Tavily domain filters not supported, retrying without filters: {e}")
                payload.pop("include_domains", None)
                payload.pop("exclude_domains", None)
                response = client.search(**payload)

            # Soft preference: re-rank results by preferred domains
            if prefer_domains and isinstance(response, dict) and response.get("results"):
                response["results"] = self._sort_by_preferred_domains(
                    response["results"], prefer_domains
                )

            return response

        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            raise

    def extract_headings(self, content: str) -> list[str]:
        """
        Extract heading structure from content.

        Args:
            content: Article content.

        Returns:
            List of headings found in the content.
        """
        import re

        # Match common heading patterns
        heading_patterns = [
            r"^#{1,3}\s+(.+)$",  # Markdown headings
            r"^【(.+)】",  # Japanese bracket headings
            r"^■\s*(.+)$",  # Bullet headings
            r"^\d+\.\s+(.+)$",  # Numbered headings
        ]

        headings = []
        for line in content.split("\n"):
            for pattern in heading_patterns:
                match = re.match(pattern, line.strip())
                if match:
                    headings.append(match.group(1).strip())
                    break

        return headings

    def search_internal_knowledge(self, query: str, top_k: int = 5) -> list[str]:
        """
        Search internal knowledge base for relevant information.

        Args:
            query: Search query.
            top_k: Number of results to return.

        Returns:
            List of relevant content snippets.
        """
        results = self.rag_service.search_knowledge_base(query, top_k=top_k)
        return [r.content for r in results]

    def analyze_content_gaps(
        self,
        competitor_content: list[str],
        internal_knowledge: list[str],
        tavily_answer: str | None = None,
    ) -> list[str]:
        """
        Analyze content gaps between competitors and internal knowledge.

        Uses GPT-4o to identify unique angles and missing topics.

        Args:
            competitor_content: Content from competitor articles.
            internal_knowledge: Content from internal knowledge base.

        Returns:
            List of identified content gaps and opportunities.
        """
        try:
            client = get_openai_client()

            tavily_section = ""
            if tavily_answer:
                tavily_section = f"\n## Tavily要約回答\n{tavily_answer[:1200]}\n"

            prompt = f"""以下の競合記事の内容と社内資料を分析し、差別化できるポイントを3-5つ挙げてください。

## 競合記事の内容
{chr(10).join(competitor_content[:3])}

## 社内資料
{chr(10).join(internal_knowledge[:3])}
{tavily_section}

## 出力形式
- 差別化ポイント1: 説明
- 差別化ポイント2: 説明
...

競合が触れていない、または深掘りしていないトピックで、社内の知見を活かせるポイントを特定してください。
"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "あなたはFP&A・経営管理の専門家です。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
            )

            content = response.choices[0].message.content
            gaps = [
                line.strip("- ").strip()
                for line in content.split("\n")
                if line.strip().startswith("-") or line.strip().startswith("・")
            ]

            return gaps if gaps else [content]

        except Exception as e:
            logger.error(f"Content gap analysis failed: {e}")
            return ["差別化分析に失敗しました。手動で競合との差別化ポイントを検討してください。"]

    def generate_outline_suggestion(
        self,
        seo_keywords: str,
        competitor_headings: list[list[str]],
        content_gaps: list[str],
        tavily_answer: str | None = None,
    ) -> list[str]:
        """
        Generate suggested article outline based on research.

        Args:
            seo_keywords: Target SEO keywords.
            competitor_headings: Headings from competitor articles.
            content_gaps: Identified content gaps.

        Returns:
            Suggested outline as a list of section headings.
        """
        try:
            client = get_openai_client()

            # Flatten competitor headings for prompt
            flat_headings = []
            for article_headings in competitor_headings[:3]:
                flat_headings.extend(article_headings[:5])

            tavily_section = ""
            if tavily_answer:
                tavily_section = f"\n## Tavily要約回答\n{tavily_answer[:1200]}\n"

            prompt = f"""以下の情報を基に、SEO上位を狙える記事の構成案を作成してください。

## ターゲットキーワード
{seo_keywords}

## 競合記事の見出し構成
{chr(10).join(flat_headings[:15])}

## 差別化ポイント
{chr(10).join(content_gaps)}
{tavily_section}

## 出力形式
1. [見出し1]
2. [見出し2]
...

読者の課題認識→解決策→実践方法→まとめ の流れで、5-7個の見出しを提案してください。
差別化ポイントを必ず1つ以上含めてください。
"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "あなたはSEOと経営管理の専門家です。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            content = response.choices[0].message.content
            outline = []
            for line in content.split("\n"):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("-")):
                    # Extract heading text
                    import re
                    match = re.match(r"[\d\.\-\s]*(.+)", line)
                    if match:
                        outline.append(match.group(1).strip())

            return outline if outline else ["導入", "課題の整理", "解決策", "実践方法", "まとめ"]

        except Exception as e:
            logger.error(f"Outline generation failed: {e}")
            return ["導入", "課題の整理", "解決策", "実践方法", "まとめ"]

    def analyze(self, seo_keywords: str, domain_profile: str | None = None) -> ResearchResult:
        """
        Perform full research analysis for given SEO keywords.

        Args:
            seo_keywords: Target SEO keywords.

        Returns:
            Complete research results.
        """
        logger.info(f"Starting research for keywords: {seo_keywords}")

        # Step 1: Search competitors
        competitor_payload = self.search_competitors(
            seo_keywords,
            domain_profile=domain_profile,
        )
        competitor_results = competitor_payload.get("results", [])
        tavily_answer = competitor_payload.get("answer", "") if isinstance(competitor_payload, dict) else ""
        urls = [r.get("url", "") for r in competitor_results]
        contents = [r.get("content", "") for r in competitor_results]

        # Step 2: Extract headings from competitor content
        headings = [self.extract_headings(c) for c in contents]

        # Step 3: Search internal knowledge
        internal_refs = self.search_internal_knowledge(seo_keywords)

        # Step 4: Analyze content gaps
        content_gaps = self.analyze_content_gaps(contents, internal_refs, tavily_answer)

        # Step 5: Generate outline suggestion
        suggested_outline = self.generate_outline_suggestion(
            seo_keywords, headings, content_gaps, tavily_answer
        )

        # Step 6: Create competitor analysis
        competitor_analysis = CompetitorAnalysis(
            urls=urls,
            headings=headings,
            content_gaps=content_gaps,
            key_points=[r.get("title", "") for r in competitor_results],
        )

        # Step 7: Generate research summary
        research_summary = self._generate_summary(
            seo_keywords,
            competitor_analysis,
            internal_refs,
            suggested_outline,
            tavily_answer,
        )

        return ResearchResult(
            competitor_analysis=competitor_analysis,
            internal_references=internal_refs,
            suggested_outline=suggested_outline,
            research_summary=research_summary,
            tavily_answer=tavily_answer,
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            netloc = urlparse(url).netloc.lower()
            return netloc
        except Exception:
            return ""

    def _sort_by_preferred_domains(self, results: list[dict], preferred_domains: list[str]) -> list[dict]:
        """Sort results so preferred domains come first (soft preference)."""
        preferred = {d.lower() for d in preferred_domains if d}
        if not preferred:
            return results

        def rank(item: dict) -> tuple[int, str]:
            url = item.get("url", "")
            domain = self._extract_domain(url)
            return (0 if any(p in domain for p in preferred) else 1, domain)

        return sorted(results, key=rank)

    def _generate_summary(
        self,
        seo_keywords: str,
        competitor_analysis: CompetitorAnalysis,
        internal_refs: list[str],
        suggested_outline: list[str],
        tavily_answer: str | None = None,
    ) -> str:
        """Generate a human-readable research summary."""
        summary_parts = [
            f"## リサーチサマリー",
            f"",
            f"**ターゲットキーワード:** {seo_keywords}",
            f"",
            f"### 競合分析",
            f"- 分析した記事数: {len(competitor_analysis.urls)}",
            f"- 主なトピック: {', '.join(competitor_analysis.key_points[:3])}",
            f"",
            f"### 差別化ポイント",
        ]

        for gap in competitor_analysis.content_gaps[:3]:
            summary_parts.append(f"- {gap}")

        summary_parts.extend([
            f"",
            f"### 推奨構成",
        ])

        for i, heading in enumerate(suggested_outline, 1):
            summary_parts.append(f"{i}. {heading}")

        if tavily_answer:
            summary_parts.extend([
                f"",
                f"### Tavily要約回答（参考）",
                tavily_answer[:1200],
            ])

        if internal_refs:
            summary_parts.extend([
                f"",
                f"### 参照可能な社内資料",
                f"- {len(internal_refs)}件の関連資料を発見",
            ])

        return "\n".join(summary_parts)
