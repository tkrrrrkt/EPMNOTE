"""
EPM Note Engine - Image Search Service

Provides image search functionality via Unsplash and Pexels APIs.
Includes Japanese to English translation for better Unsplash results.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings, get_openai_client

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    """Result from image search."""

    id: str
    url_small: str  # Preview (400px)
    url_regular: str  # Article use (1080px)
    url_full: str  # Original
    alt_text: str
    author: str
    source: Literal["unsplash", "pexels"]
    download_url: str


@dataclass
class ImageSearchResult:
    """Aggregated image search results."""

    query: str
    images: list[ImageResult] = field(default_factory=list)
    source_used: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONB storage."""
        return {
            "query": self.query,
            "source": self.source_used,
            "images": [
                {
                    "id": img.id,
                    "url_small": img.url_small,
                    "url_regular": img.url_regular,
                    "alt_text": img.alt_text,
                    "author": img.author,
                    "source": img.source,
                }
                for img in self.images
            ],
            "error": self.error_message,
        }


class ImageService:
    """
    Image search service using Unsplash and Pexels APIs.

    Prioritizes Unsplash (higher quality for business use),
    falls back to Pexels if Unsplash is unavailable.
    """

    UNSPLASH_BASE_URL = "https://api.unsplash.com"
    PEXELS_BASE_URL = "https://api.pexels.com/v1"

    def __init__(self) -> None:
        """Initialize the image service."""
        self.settings = get_settings()
        self._client = httpx.Client(timeout=10.0)
        self._openai_client = None
        self._translation_cache: dict[str, str] = {}

    def __del__(self) -> None:
        """Clean up HTTP client."""
        try:
            self._client.close()
        except Exception:
            pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def search_images(
        self,
        query: str,
        per_page: int = 5,
        locale: str = "ja",
    ) -> ImageSearchResult:
        """
        Search for images matching the query.

        Args:
            query: Search query (Japanese supported)
            per_page: Number of results per page
            locale: Locale for search (default: Japanese)

        Returns:
            ImageSearchResult with matched images
        """
        # Try Unsplash first (with English translation for better results)
        if self.settings.unsplash_access_key:
            # Translate Japanese to English for Unsplash
            english_query = self._translate_to_english(query)
            logger.info(f"Unsplash search: '{query}' -> '{english_query}'")
            result = self._search_unsplash(english_query, per_page)
            if result.images:
                # Keep original Japanese query in result for display
                result.query = query
                return result

        # Fallback to Pexels (supports Japanese directly)
        if self.settings.pexels_api_key:
            result = self._search_pexels(query, per_page, locale)
            if result.images:
                return result

        return ImageSearchResult(
            query=query,
            error_message="画像APIが設定されていないか、検索結果がありません。UNSPLASH_ACCESS_KEY または PEXELS_API_KEY を.envに設定してください。",
        )

    def _search_unsplash(self, query: str, per_page: int) -> ImageSearchResult:
        """Search Unsplash API."""
        try:
            response = self._client.get(
                f"{self.UNSPLASH_BASE_URL}/search/photos",
                params={
                    "query": query,
                    "per_page": per_page,
                    "content_filter": "high",  # Safe content only
                },
                headers={
                    "Authorization": f"Client-ID {self.settings.unsplash_access_key}"
                },
            )
            response.raise_for_status()
            data = response.json()

            images = [
                ImageResult(
                    id=photo["id"],
                    url_small=photo["urls"]["small"],
                    url_regular=photo["urls"]["regular"],
                    url_full=photo["urls"]["full"],
                    alt_text=photo.get("alt_description", "") or "",
                    author=photo["user"]["name"],
                    source="unsplash",
                    download_url=photo["links"]["download_location"],
                )
                for photo in data.get("results", [])
            ]

            return ImageSearchResult(query=query, images=images, source_used="unsplash")

        except httpx.HTTPStatusError as e:
            logger.warning(f"Unsplash search failed with status {e.response.status_code}: {e}")
            return ImageSearchResult(query=query, error_message=f"Unsplash API error: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Unsplash search failed: {e}")
            return ImageSearchResult(query=query, error_message=str(e))

    def _search_pexels(self, query: str, per_page: int, locale: str) -> ImageSearchResult:
        """Search Pexels API."""
        try:
            response = self._client.get(
                f"{self.PEXELS_BASE_URL}/search",
                params={
                    "query": query,
                    "per_page": per_page,
                    "locale": locale,
                },
                headers={
                    "Authorization": self.settings.pexels_api_key
                },
            )
            response.raise_for_status()
            data = response.json()

            images = [
                ImageResult(
                    id=str(photo["id"]),
                    url_small=photo["src"]["small"],
                    url_regular=photo["src"]["large"],
                    url_full=photo["src"]["original"],
                    alt_text=photo.get("alt", "") or "",
                    author=photo["photographer"],
                    source="pexels",
                    download_url=photo["src"]["original"],
                )
                for photo in data.get("photos", [])
            ]

            return ImageSearchResult(query=query, images=images, source_used="pexels")

        except httpx.HTTPStatusError as e:
            logger.warning(f"Pexels search failed with status {e.response.status_code}: {e}")
            return ImageSearchResult(query=query, error_message=f"Pexels API error: {e.response.status_code}")
        except Exception as e:
            logger.warning(f"Pexels search failed: {e}")
            return ImageSearchResult(query=query, error_message=str(e))

    def search_for_prompts(
        self,
        prompts: list[str],
        images_per_prompt: int = 3,
    ) -> list[ImageSearchResult]:
        """
        Search images for multiple prompts (from WriterAgent).

        Args:
            prompts: List of image prompts from WriterAgent
            images_per_prompt: Number of images to fetch per prompt

        Returns:
            List of ImageSearchResult for each prompt
        """
        results = []
        for prompt in prompts:
            # Extract search keywords from prompt
            keywords = self._extract_keywords_from_prompt(prompt)
            result = self.search_images(keywords, per_page=images_per_prompt)
            results.append(result)
        return results

    def _extract_keywords_from_prompt(self, prompt: str) -> str:
        """
        Extract searchable keywords from image prompt.

        WriterAgent generates prompts like:
        ### 図解1: 予算管理サイクル
        - 目的: PDCAサイクルを可視化
        - 形式: フロー図

        This extracts key terms for image search.
        """
        # Extract title after "図解N:"
        title_match = re.search(r"図解\d+:\s*(.+)", prompt)
        if title_match:
            return title_match.group(1).strip()

        # Extract purpose after "目的:"
        purpose_match = re.search(r"目的:\s*(.+)", prompt)
        if purpose_match:
            return purpose_match.group(1).strip()

        # Fallback: first non-empty line that's not a header or list item
        for line in prompt.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                return line[:50]

        return prompt[:50]

    def is_available(self) -> bool:
        """Check if any image API is configured."""
        return bool(self.settings.unsplash_access_key or self.settings.pexels_api_key)

    def _translate_to_english(self, text: str) -> str:
        """
        Translate Japanese text to English for better Unsplash search results.

        Uses OpenAI API for translation. Falls back to original text if translation fails.
        Results are cached to avoid redundant API calls.
        """
        # Return as-is if already English (simple check)
        if text.isascii():
            return text

        # Check cache
        if text in self._translation_cache:
            return self._translation_cache[text]

        # Try OpenAI translation
        if not self.settings.openai_api_key:
            logger.warning("OpenAI API key not configured, skipping translation")
            return text

        try:
            if self._openai_client is None:
                self._openai_client = get_openai_client()

            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a translator. Translate the given Japanese text to English keywords suitable for image search. Output ONLY the English keywords, nothing else. Keep it concise (2-5 words)."
                    },
                    {
                        "role": "user",
                        "content": text
                    }
                ],
                max_tokens=50,
                temperature=0.3,
            )

            english_text = response.choices[0].message.content.strip()

            # Cache the result
            self._translation_cache[text] = english_text

            return english_text

        except Exception as e:
            logger.warning(f"Translation failed: {e}, using original text")
            return text

    # ===========================================
    # SEO Enhancement Methods (v1.2)
    # ===========================================

    def generate_alt_text(self, query: str, article_context: str = "") -> str:
        """
        Generate SEO-optimized alt text for an image.

        Uses Claude Haiku for cost efficiency.

        Args:
            query: The search query used to find the image.
            article_context: Article title or context (optional).

        Returns:
            Generated alt text (50-100 characters).
        """
        try:
            from src.config import get_anthropic_client
            client = get_anthropic_client()
            if not client:
                return query  # Fallback to query

            prompt = f"""画像のalt属性テキストを生成してください。

## 画像検索キーワード
{query}

## 記事テーマ（参考）
{article_context[:200] if article_context else "（なし）"}

## 要件
- 50-100文字（日本語）
- 画像の内容を具体的に説明
- SEOを意識（キーワードを自然に含める）
- 視覚障害者にも伝わる描写

## 出力
alt属性テキストのみを出力（説明不要）。
"""

            response = client.messages.create(
                model="claude-haiku-3-5-20241022",
                max_tokens=150,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            alt_text = response.content[0].text.strip()
            # Ensure length constraint
            if len(alt_text) > 100:
                alt_text = alt_text[:97] + "..."
            return alt_text

        except Exception as e:
            logger.warning(f"Alt text generation failed: {e}")
            return query  # Fallback to query

    def insert_images_to_markdown(
        self,
        content: str,
        image_suggestions: list[dict],
    ) -> str:
        """
        Insert images into markdown content at appropriate positions.

        Insertion rules:
        1. First image after "## 目次" as eyecatch
        2. Subsequent images after each major "## " heading

        Args:
            content: Markdown content.
            image_suggestions: List of image search results from search_for_prompts.

        Returns:
            Markdown content with images inserted.
        """
        if not image_suggestions:
            return content

        # Flatten images from all suggestions
        all_images = []
        for suggestion in image_suggestions:
            images = suggestion.get("images", [])
            for img in images[:1]:  # Take first image from each suggestion
                all_images.append({
                    "url": img.get("url_regular", ""),
                    "alt": img.get("alt_text", "") or suggestion.get("query", ""),
                    "author": img.get("author", ""),
                    "source": img.get("source", ""),
                })

        if not all_images:
            return content

        lines = content.split("\n")
        result_lines = []
        image_index = 0
        toc_found = False

        for i, line in enumerate(lines):
            result_lines.append(line)

            # Insert first image after "## 目次"
            if not toc_found and line.strip().startswith("## 目次"):
                toc_found = True
                # Find end of TOC section (next empty line or heading)
                continue

            # Insert image after TOC ends
            if toc_found and image_index == 0:
                # Check if this is the end of TOC section
                if (line.strip() == "" or
                    (line.strip().startswith("##") and "目次" not in line)):
                    if image_index < len(all_images):
                        img = all_images[image_index]
                        image_md = self._format_image_markdown(img)
                        result_lines.append("")
                        result_lines.append(image_md)
                        result_lines.append("")
                        image_index += 1
                    continue

            # Insert subsequent images after major headings (## but not ###)
            if (line.strip().startswith("## ") and
                not line.strip().startswith("### ") and
                "目次" not in line and
                "次に読む" not in line and
                "チェックリスト" not in line and
                image_index > 0 and
                image_index < len(all_images)):

                # Look ahead to find end of section intro (after 2-3 paragraphs)
                para_count = 0
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].strip() == "":
                        para_count += 1
                    if para_count >= 2:
                        break

        return "\n".join(result_lines)

    def _format_image_markdown(self, image: dict) -> str:
        """Format an image as markdown with proper attribution."""
        url = image.get("url", "")
        alt = image.get("alt", "")
        author = image.get("author", "")
        source = image.get("source", "")

        # Create markdown image
        md = f"![{alt}]({url})"

        # Add attribution as caption
        if author and source:
            md += f"\n*Photo by {author} on {source.capitalize()}*"

        return md

    def enhance_image_suggestions(
        self,
        suggestions: list[dict],
        article_context: str = "",
    ) -> list[dict]:
        """
        Enhance image suggestions with generated alt text.

        Args:
            suggestions: Raw image suggestions from search_for_prompts.
            article_context: Article title/context for better alt text.

        Returns:
            Enhanced suggestions with better alt text.
        """
        enhanced = []
        for suggestion in suggestions:
            enhanced_suggestion = suggestion.copy()
            enhanced_images = []

            for img in suggestion.get("images", []):
                enhanced_img = img.copy()
                # Generate alt text if missing or generic
                if not enhanced_img.get("alt_text") or len(enhanced_img.get("alt_text", "")) < 10:
                    query = suggestion.get("query", "")
                    enhanced_img["alt_text"] = self.generate_alt_text(query, article_context)
                enhanced_images.append(enhanced_img)

            enhanced_suggestion["images"] = enhanced_images
            enhanced.append(enhanced_suggestion)

        return enhanced
