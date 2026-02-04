"""
EPM Note Engine - Internal Link Service

Provides internal link suggestions based on article content similarity.
"""

import logging
from dataclasses import dataclass, field

from src.database.connection import get_session
from src.database.models import Article, ArticleStatus
from src.repositories.article_repository import ArticleRepository

logger = logging.getLogger(__name__)


@dataclass
class LinkSuggestion:
    """A suggested internal link."""

    article_id: str
    title: str
    url: str | None
    relevance_score: float
    snippet: str = ""  # Preview of the article content


@dataclass
class LinkSuggestionResult:
    """Result of internal link suggestion."""

    suggestions: list[LinkSuggestion] = field(default_factory=list)
    source_keywords: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONB storage."""
        return {
            "suggestions": [
                {
                    "article_id": s.article_id,
                    "title": s.title,
                    "url": s.url,
                    "relevance_score": s.relevance_score,
                    "snippet": s.snippet,
                }
                for s in self.suggestions
            ],
            "source_keywords": self.source_keywords,
            "error": self.error_message,
        }


class LinkService:
    """
    Service for suggesting internal links between articles.

    Uses keyword matching and RAG similarity to find related articles.
    """

    def __init__(self) -> None:
        """Initialize the link service."""
        pass

    def suggest_internal_links(
        self,
        content: str,
        exclude_article_id: str | None = None,
        max_suggestions: int = 5,
    ) -> LinkSuggestionResult:
        """
        Suggest internal links for an article.

        Args:
            content: Article content to find related links for.
            exclude_article_id: Article ID to exclude from suggestions.
            max_suggestions: Maximum number of suggestions to return.

        Returns:
            LinkSuggestionResult with suggested articles.
        """
        logger.info("Generating internal link suggestions")

        # Extract keywords from content
        keywords = self._extract_keywords(content)
        if not keywords:
            return LinkSuggestionResult(
                error_message="キーワードを抽出できませんでした"
            )

        # Find related articles
        suggestions = self._find_related_articles(
            keywords,
            exclude_article_id,
            max_suggestions,
        )

        return LinkSuggestionResult(
            suggestions=suggestions,
            source_keywords=keywords,
        )

    def _extract_keywords(self, content: str, max_keywords: int = 10) -> list[str]:
        """
        Extract important keywords from content for similarity matching.

        Uses simple heuristics: headings, bold text, and repeated terms.
        """
        import re

        keywords = []

        # Extract from headings (## and ###)
        headings = re.findall(r"^##?\s+(.+)$", content, re.MULTILINE)
        for heading in headings[:5]:
            # Clean heading
            clean = re.sub(r"[【】「」『』（）\[\]\d\.\:\：]", " ", heading)
            keywords.extend(clean.split())

        # Extract from bold text
        bold_texts = re.findall(r"\*\*([^*]+)\*\*", content)
        for text in bold_texts[:10]:
            if len(text) < 20:  # Skip long bold sections
                keywords.append(text)

        # Clean and dedupe
        cleaned = []
        seen = set()
        for kw in keywords:
            kw = kw.strip()
            if kw and len(kw) >= 2 and kw.lower() not in seen:
                # Skip common words
                if kw not in ["必須", "重要", "注意", "ポイント", "方法", "例"]:
                    cleaned.append(kw)
                    seen.add(kw.lower())

        return cleaned[:max_keywords]

    def _find_related_articles(
        self,
        keywords: list[str],
        exclude_id: str | None,
        max_results: int,
    ) -> list[LinkSuggestion]:
        """
        Find articles related to the given keywords.

        Uses keyword matching against article titles and SEO keywords.
        """
        suggestions = []

        with get_session() as session:
            repo = ArticleRepository(session)

            # Get all completed or published articles
            all_articles = list(repo.get_all())
            candidates = [
                a for a in all_articles
                if a.status in [ArticleStatus.COMPLETED, ArticleStatus.REVIEW]
                and (exclude_id is None or a.id != exclude_id)
            ]

            # Score each candidate
            scored = []
            for article in candidates:
                score = self._calculate_relevance(article, keywords)
                if score > 0:
                    scored.append((article, score))

            # Sort by score and take top results
            scored.sort(key=lambda x: x[1], reverse=True)

            for article, score in scored[:max_results]:
                snippet = ""
                if article.draft_content_md:
                    # Take first 100 chars of content as snippet
                    snippet = article.draft_content_md[:100].replace("\n", " ")
                    if len(article.draft_content_md) > 100:
                        snippet += "..."

                suggestions.append(
                    LinkSuggestion(
                        article_id=article.id,
                        title=article.title,
                        url=article.published_url,
                        relevance_score=score,
                        snippet=snippet,
                    )
                )

        return suggestions

    def _calculate_relevance(self, article: Article, keywords: list[str]) -> float:
        """
        Calculate relevance score between an article and keywords.

        Returns a score from 0 to 1.
        """
        score = 0.0
        max_score = len(keywords) * 3  # Max 3 points per keyword

        title_lower = article.title.lower()
        seo_keywords_lower = (article.seo_keywords or "").lower()
        content_lower = (article.draft_content_md or "")[:1000].lower()

        for kw in keywords:
            kw_lower = kw.lower()

            # Title match (highest weight)
            if kw_lower in title_lower:
                score += 3

            # SEO keyword match (medium weight)
            elif kw_lower in seo_keywords_lower:
                score += 2

            # Content match (low weight)
            elif kw_lower in content_lower:
                score += 1

        # Normalize to 0-1
        if max_score > 0:
            return min(score / max_score, 1.0)
        return 0.0

    def suggest_links_with_rag(
        self,
        content: str,
        exclude_article_id: str | None = None,
        max_suggestions: int = 5,
    ) -> LinkSuggestionResult:
        """
        Suggest internal links using RAG similarity search.

        This method uses the RAG service to find semantically similar content.

        Args:
            content: Article content.
            exclude_article_id: Article ID to exclude.
            max_suggestions: Maximum suggestions.

        Returns:
            LinkSuggestionResult with RAG-based suggestions.
        """
        try:
            from src.repositories.rag_service import RAGService
            rag = RAGService()

            # Search for similar content in knowledge base
            # Note: This searches documents, not articles directly
            results = rag.search_knowledge_base(content[:500], top_k=10)

            # For now, fall back to keyword-based search
            # Future enhancement: Add article embeddings to ChromaDB
            return self.suggest_internal_links(content, exclude_article_id, max_suggestions)

        except Exception as e:
            logger.warning(f"RAG-based link suggestion failed: {e}")
            return self.suggest_internal_links(content, exclude_article_id, max_suggestions)
