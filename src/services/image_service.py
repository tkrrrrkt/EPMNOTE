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
