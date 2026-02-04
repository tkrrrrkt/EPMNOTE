"""
EPM Note Engine - Research Agent

Performs SEO competitor analysis using Tavily API and internal knowledge search.
Includes keyword density analysis using Janome for Japanese NLP.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    get_openai_client,
    get_settings,
    get_tavily_client,
    resolve_tavily_domains,
)
from src.repositories.rag_service import RAGService

logger = logging.getLogger(__name__)

# Try to import Janome for Japanese NLP
try:
    from janome.tokenizer import Tokenizer
    JANOME_AVAILABLE = True
except ImportError:
    JANOME_AVAILABLE = False
    logger.warning("Janome not installed. Keyword analysis will be limited.")


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


@dataclass
class KeywordOccurrence:
    """Single keyword occurrence analysis."""

    keyword: str
    count: int
    density: float  # Percentage of total words
    positions: list[str] = field(default_factory=list)  # ["title", "h2", "body", ...]
    in_first_paragraph: bool = False
    in_conclusion: bool = False


@dataclass
class KeywordAnalysis:
    """Complete keyword analysis results."""

    target_keywords: list[str] = field(default_factory=list)
    total_words: int = 0
    total_characters: int = 0

    # Primary keyword analysis
    primary_keyword: KeywordOccurrence | None = None

    # Related keywords found
    related_keywords: list[KeywordOccurrence] = field(default_factory=list)

    # SEO metrics (0-100)
    keyword_density_score: float = 0.0
    placement_score: float = 0.0
    overall_seo_score: float = 0.0

    # Suggestions
    suggestions: list[str] = field(default_factory=list)

    # Raw frequency data
    noun_frequency: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        return {
            "target_keywords": self.target_keywords,
            "total_words": self.total_words,
            "total_characters": self.total_characters,
            "primary_keyword": {
                "keyword": self.primary_keyword.keyword,
                "count": self.primary_keyword.count,
                "density": self.primary_keyword.density,
                "positions": self.primary_keyword.positions,
                "in_first_paragraph": self.primary_keyword.in_first_paragraph,
                "in_conclusion": self.primary_keyword.in_conclusion,
            } if self.primary_keyword else None,
            "related_keywords": [
                {
                    "keyword": kw.keyword,
                    "count": kw.count,
                    "density": kw.density,
                    "positions": kw.positions,
                }
                for kw in self.related_keywords[:10]
            ],
            "keyword_density_score": self.keyword_density_score,
            "placement_score": self.placement_score,
            "overall_seo_score": self.overall_seo_score,
            "suggestions": self.suggestions,
            "top_nouns": dict(sorted(
                self.noun_frequency.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]),
        }


@dataclass
class CompetitorKeyword:
    """Keyword extracted from competitor articles."""

    keyword: str
    article_count: int  # How many articles use this keyword
    total_articles: int  # Total articles analyzed
    usage_rate: float  # article_count / total_articles * 100
    found_in_titles: int  # How many article titles contain this
    found_in_headings: int  # How many article headings contain this
    priority: str  # "必須", "推奨", "検討"


@dataclass
class CompetitorKeywordResult:
    """Result of competitor keyword extraction."""

    query: str
    total_articles: int = 0
    keywords: list[CompetitorKeyword] = field(default_factory=list)
    article_titles: list[str] = field(default_factory=list)
    article_urls: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSONB storage."""
        return {
            "query": self.query,
            "total_articles": self.total_articles,
            "keywords": [
                {
                    "keyword": kw.keyword,
                    "article_count": kw.article_count,
                    "total_articles": kw.total_articles,
                    "usage_rate": kw.usage_rate,
                    "found_in_titles": kw.found_in_titles,
                    "found_in_headings": kw.found_in_headings,
                    "priority": kw.priority,
                }
                for kw in self.keywords
            ],
            "article_titles": self.article_titles,
            "article_urls": self.article_urls,
            "suggestions": self.suggestions,
        }


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

    # ===========================================
    # Keyword Analysis Methods
    # ===========================================

    def analyze_keyword_density(
        self,
        content: str,
        target_keywords: list[str],
    ) -> KeywordAnalysis:
        """
        Analyze keyword density and placement in content.

        Args:
            content: Article content in Markdown format.
            target_keywords: Target SEO keywords to analyze.

        Returns:
            KeywordAnalysis with metrics and suggestions.
        """
        if not JANOME_AVAILABLE:
            return KeywordAnalysis(
                target_keywords=target_keywords,
                total_words=len(content.split()),
                total_characters=len(content),
                suggestions=["Janomeがインストールされていないため、詳細分析ができません。pip install janome を実行してください。"],
            )

        # Initialize tokenizer lazily
        if not hasattr(self, "_tokenizer"):
            self._tokenizer = Tokenizer()

        # Parse content sections
        sections = self._parse_content_sections(content)

        # Tokenize and count
        tokens = list(self._tokenizer.tokenize(content))
        nouns = [
            t.surface
            for t in tokens
            if t.part_of_speech.startswith("名詞")
            and len(t.surface) > 1
            and not t.surface.isdigit()
        ]

        total_words = len(tokens)
        total_chars = len(content)

        # Count noun frequency
        noun_freq: dict[str, int] = {}
        for noun in nouns:
            noun_freq[noun] = noun_freq.get(noun, 0) + 1

        # Analyze target keywords
        primary_kw = None
        related_kws = []

        for keyword in target_keywords:
            if not keyword.strip():
                continue
            occurrence = self._analyze_keyword_occurrence(
                keyword.strip(), content, sections, total_words
            )
            if primary_kw is None:
                primary_kw = occurrence
            else:
                related_kws.append(occurrence)

        # Find additional related keywords from content
        for noun, count in sorted(noun_freq.items(), key=lambda x: x[1], reverse=True)[:15]:
            if noun not in target_keywords and count >= 3:
                occurrence = self._analyze_keyword_occurrence(
                    noun, content, sections, total_words
                )
                related_kws.append(occurrence)

        # Calculate scores
        density_score = self._calculate_density_score(primary_kw)
        placement_score = self._calculate_placement_score(primary_kw)
        overall_score = (density_score * 0.4 + placement_score * 0.6)

        # Generate suggestions
        suggestions = self._generate_seo_suggestions(
            primary_kw, related_kws, density_score, placement_score
        )

        return KeywordAnalysis(
            target_keywords=target_keywords,
            total_words=total_words,
            total_characters=total_chars,
            primary_keyword=primary_kw,
            related_keywords=related_kws[:10],
            keyword_density_score=density_score,
            placement_score=placement_score,
            overall_seo_score=overall_score,
            suggestions=suggestions,
            noun_frequency=noun_freq,
        )

    def _parse_content_sections(self, content: str) -> dict[str, Any]:
        """Parse Markdown content into sections."""
        sections: dict[str, Any] = {
            "title": "",
            "first_paragraph": "",
            "h2_headings": [],
            "h3_headings": [],
            "body": content,
            "conclusion": "",
        }

        lines = content.split("\n")

        # Extract title (first H1)
        for line in lines:
            if line.startswith("# "):
                sections["title"] = line[2:].strip()
                break

        # Extract first paragraph (first non-heading, non-empty block)
        in_first_para = False
        first_para_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_first_para:
                    break
                continue
            if stripped.startswith("#"):
                if in_first_para:
                    break
                continue
            in_first_para = True
            first_para_lines.append(stripped)
        sections["first_paragraph"] = " ".join(first_para_lines)

        # Extract H2/H3 headings
        sections["h2_headings"] = re.findall(r"^## (.+)$", content, re.MULTILINE)
        sections["h3_headings"] = re.findall(r"^### (.+)$", content, re.MULTILINE)

        # Extract conclusion (content after last H2 containing "まとめ" or after ---)
        conclusion_patterns = [r"## .*まとめ", r"## .*終わり", r"---\s*$"]
        for pattern in conclusion_patterns:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                sections["conclusion"] = content[match.start():]
                break

        return sections

    def _analyze_keyword_occurrence(
        self,
        keyword: str,
        content: str,
        sections: dict[str, Any],
        total_words: int,
    ) -> KeywordOccurrence:
        """Analyze a single keyword's occurrence in content."""
        # Count occurrences (case-insensitive)
        count = len(re.findall(re.escape(keyword), content, re.IGNORECASE))
        density = (count / max(total_words, 1)) * 100

        # Check positions
        positions = []
        if keyword.lower() in sections["title"].lower():
            positions.append("title")
        if any(keyword.lower() in h.lower() for h in sections["h2_headings"]):
            positions.append("h2")
        if any(keyword.lower() in h.lower() for h in sections["h3_headings"]):
            positions.append("h3")
        if keyword.lower() in sections["first_paragraph"].lower():
            positions.append("first_paragraph")
        if keyword.lower() in sections["conclusion"].lower():
            positions.append("conclusion")
        if keyword.lower() in sections["body"].lower():
            positions.append("body")

        return KeywordOccurrence(
            keyword=keyword,
            count=count,
            density=round(density, 2),
            positions=positions,
            in_first_paragraph="first_paragraph" in positions,
            in_conclusion="conclusion" in positions,
        )

    def _calculate_density_score(self, primary_kw: KeywordOccurrence | None) -> float:
        """Calculate keyword density score (0-100)."""
        if not primary_kw:
            return 0.0

        # Ideal density is 1-2% for Japanese content
        density = primary_kw.density
        if density < 0.5:
            score = density * 100  # Too low
        elif density <= 2.0:
            score = 100.0  # Optimal range
        elif density <= 3.0:
            score = 100 - (density - 2.0) * 50  # Starting to be too high
        else:
            score = max(0, 50 - (density - 3.0) * 20)  # Too high

        return min(100.0, max(0.0, score))

    def _calculate_placement_score(self, primary_kw: KeywordOccurrence | None) -> float:
        """Calculate keyword placement score (0-100)."""
        if not primary_kw:
            return 0.0

        score = 0.0
        positions = primary_kw.positions

        # Weight each position
        if "title" in positions:
            score += 30
        if "h2" in positions:
            score += 20
        if "first_paragraph" in positions:
            score += 25
        if "conclusion" in positions:
            score += 15
        if "h3" in positions:
            score += 10

        return min(100.0, score)

    def _generate_seo_suggestions(
        self,
        primary_kw: KeywordOccurrence | None,
        related_kws: list[KeywordOccurrence],
        density_score: float,
        placement_score: float,
    ) -> list[str]:
        """Generate SEO improvement suggestions."""
        suggestions = []

        if not primary_kw:
            suggestions.append("ターゲットキーワードが設定されていません")
            return suggestions

        # Density suggestions
        if primary_kw.density < 0.5:
            suggestions.append(
                f"キーワード「{primary_kw.keyword}」の出現率が低い（{primary_kw.density}%）。"
                "1-2%程度を目標に、自然な形で追加してください。"
            )
        elif primary_kw.density > 3.0:
            suggestions.append(
                f"キーワード「{primary_kw.keyword}」の出現率が高すぎる（{primary_kw.density}%）。"
                "キーワードスタッフィングと判断される可能性があります。"
            )

        # Placement suggestions
        if "title" not in primary_kw.positions:
            suggestions.append(
                f"タイトルにキーワード「{primary_kw.keyword}」を含めてください（SEO重要度: 高）"
            )
        if "first_paragraph" not in primary_kw.positions:
            suggestions.append(
                f"冒頭の段落にキーワード「{primary_kw.keyword}」を含めてください"
            )
        if "h2" not in primary_kw.positions:
            suggestions.append(
                f"H2見出しにキーワード「{primary_kw.keyword}」を含めてください"
            )

        # Related keyword suggestions
        high_freq_related = [kw for kw in related_kws if kw.count >= 5][:3]
        if high_freq_related:
            kw_list = "、".join([kw.keyword for kw in high_freq_related])
            suggestions.append(
                f"関連キーワード（{kw_list}）が多く出現しています。"
                "これらを意図的に活用することで、トピックの網羅性を高められます。"
            )

        if not suggestions:
            suggestions.append("キーワード最適化は良好です")

        return suggestions

    # ===========================================
    # Competitor Keyword Extraction Methods
    # ===========================================

    def extract_competitor_keywords(
        self,
        query: str,
        max_articles: int = 10,
    ) -> CompetitorKeywordResult:
        """
        Extract common keywords from competitor articles via Tavily search.

        Args:
            query: Search query (e.g., "予算管理")
            max_articles: Maximum number of articles to analyze.

        Returns:
            CompetitorKeywordResult with extracted keywords and usage stats.
        """
        logger.info(f"Extracting competitor keywords for: {query}")

        # Search for competitor articles
        try:
            tavily_response = self.search_competitors(query, max_results=max_articles)
        except Exception as e:
            logger.error(f"Failed to search competitors: {e}")
            return CompetitorKeywordResult(
                query=query,
                suggestions=[f"競合検索に失敗しました: {e}"],
            )

        results = tavily_response.get("results", [])
        if not results:
            return CompetitorKeywordResult(
                query=query,
                suggestions=["競合記事が見つかりませんでした"],
            )

        # Extract titles and content from results
        article_titles = []
        article_urls = []
        all_text_parts = []  # Combined titles + headings for analysis

        for result in results:
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")

            if title:
                article_titles.append(title)
                all_text_parts.append(("title", title))
            if url:
                article_urls.append(url)

            # Extract headings from content
            headings = self.extract_headings(content)
            for heading in headings:
                all_text_parts.append(("heading", heading))

        total_articles = len(article_titles)

        # Extract and count keywords using Janome
        keyword_stats = self._extract_keywords_from_texts(
            all_text_parts, article_titles, total_articles
        )

        # Sort by usage rate and create CompetitorKeyword objects
        sorted_keywords = sorted(
            keyword_stats.items(),
            key=lambda x: (x[1]["article_count"], x[1]["found_in_titles"]),
            reverse=True,
        )

        keywords = []
        for keyword, stats in sorted_keywords[:20]:  # Top 20 keywords
            usage_rate = (stats["article_count"] / max(total_articles, 1)) * 100

            # Determine priority based on usage rate
            if usage_rate >= 70:
                priority = "必須"
            elif usage_rate >= 40:
                priority = "推奨"
            else:
                priority = "検討"

            keywords.append(CompetitorKeyword(
                keyword=keyword,
                article_count=stats["article_count"],
                total_articles=total_articles,
                usage_rate=round(usage_rate, 1),
                found_in_titles=stats["found_in_titles"],
                found_in_headings=stats["found_in_headings"],
                priority=priority,
            ))

        # Generate suggestions
        suggestions = self._generate_competitor_keyword_suggestions(keywords, query)

        return CompetitorKeywordResult(
            query=query,
            total_articles=total_articles,
            keywords=keywords,
            article_titles=article_titles,
            article_urls=article_urls,
            suggestions=suggestions,
        )

    def _extract_keywords_from_texts(
        self,
        text_parts: list[tuple[str, str]],  # [("title", "text"), ("heading", "text")]
        article_titles: list[str],
        total_articles: int,
    ) -> dict[str, dict[str, int]]:
        """
        Extract keywords from text parts and count their occurrences.

        Returns:
            Dict mapping keyword -> {"article_count": N, "found_in_titles": N, "found_in_headings": N}
        """
        keyword_stats: dict[str, dict[str, int]] = {}

        if not JANOME_AVAILABLE:
            # Fallback: simple word extraction
            return self._extract_keywords_simple(text_parts, article_titles)

        # Initialize tokenizer lazily
        if not hasattr(self, "_tokenizer"):
            self._tokenizer = Tokenizer()

        # Track which articles contain each keyword
        keyword_articles: dict[str, set[int]] = {}
        keyword_titles: dict[str, int] = {}
        keyword_headings: dict[str, int] = {}

        for idx, (text_type, text) in enumerate(text_parts):
            # Tokenize and extract nouns
            tokens = list(self._tokenizer.tokenize(text))
            nouns = set()

            for token in tokens:
                if token.part_of_speech.startswith("名詞"):
                    surface = token.surface
                    # Filter out short words and numbers
                    if len(surface) >= 2 and not surface.isdigit():
                        nouns.add(surface)

            # Also extract compound nouns (2-gram)
            token_surfaces = [t.surface for t in tokens if t.part_of_speech.startswith("名詞")]
            for i in range(len(token_surfaces) - 1):
                compound = token_surfaces[i] + token_surfaces[i + 1]
                if len(compound) >= 3:
                    nouns.add(compound)

            # Update stats for each noun
            article_idx = idx // 2  # Rough mapping to article index
            for noun in nouns:
                if noun not in keyword_articles:
                    keyword_articles[noun] = set()
                    keyword_titles[noun] = 0
                    keyword_headings[noun] = 0

                keyword_articles[noun].add(article_idx)

                if text_type == "title":
                    keyword_titles[noun] += 1
                elif text_type == "heading":
                    keyword_headings[noun] += 1

        # Build final stats
        for keyword in keyword_articles:
            keyword_stats[keyword] = {
                "article_count": len(keyword_articles[keyword]),
                "found_in_titles": keyword_titles.get(keyword, 0),
                "found_in_headings": keyword_headings.get(keyword, 0),
            }

        return keyword_stats

    def _extract_keywords_simple(
        self,
        text_parts: list[tuple[str, str]],
        article_titles: list[str],
    ) -> dict[str, dict[str, int]]:
        """Simple keyword extraction without Janome (fallback)."""
        keyword_stats: dict[str, dict[str, int]] = {}

        # Common Japanese stop words to filter
        stop_words = {"の", "は", "が", "を", "に", "で", "と", "も", "や", "へ", "から", "まで", "より", "など"}

        for text_type, text in text_parts:
            # Simple split by common delimiters
            words = re.split(r"[【】「」\s\-\|｜・、。！？\n]+", text)

            for word in words:
                word = word.strip()
                if len(word) >= 2 and word not in stop_words:
                    if word not in keyword_stats:
                        keyword_stats[word] = {
                            "article_count": 0,
                            "found_in_titles": 0,
                            "found_in_headings": 0,
                        }
                    keyword_stats[word]["article_count"] += 1
                    if text_type == "title":
                        keyword_stats[word]["found_in_titles"] += 1
                    elif text_type == "heading":
                        keyword_stats[word]["found_in_headings"] += 1

        return keyword_stats

    def _generate_competitor_keyword_suggestions(
        self,
        keywords: list[CompetitorKeyword],
        query: str,
    ) -> list[str]:
        """Generate suggestions based on competitor keyword analysis."""
        suggestions = []

        # Find must-have keywords
        must_have = [kw for kw in keywords if kw.priority == "必須"]
        if must_have:
            kw_list = "、".join([kw.keyword for kw in must_have[:5]])
            suggestions.append(
                f"必須キーワード: {kw_list} （競合の70%以上が使用）"
            )

        # Find recommended keywords
        recommended = [kw for kw in keywords if kw.priority == "推奨"]
        if recommended:
            kw_list = "、".join([kw.keyword for kw in recommended[:5]])
            suggestions.append(
                f"推奨キーワード: {kw_list} （競合の40-70%が使用）"
            )

        # Keywords frequently in titles (high SEO value)
        title_keywords = [kw for kw in keywords if kw.found_in_titles >= 3]
        if title_keywords:
            kw_list = "、".join([kw.keyword for kw in title_keywords[:3]])
            suggestions.append(
                f"タイトルに入れるべきキーワード: {kw_list}"
            )

        # Check if query itself is being used
        query_used = any(query in kw.keyword or kw.keyword in query for kw in keywords[:10])
        if not query_used:
            suggestions.append(
                f"検索クエリ「{query}」自体も記事に含めてください"
            )

        if not suggestions:
            suggestions.append("競合キーワード分析が完了しました")

        return suggestions
