"""
Unit tests for EPM Note Engine - Image Search Service.

Tests ImageService with mocked API responses.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from src.services.image_service import (
    ImageService,
    ImageResult,
    ImageSearchResult,
)


class TestImageResult:
    """Tests for ImageResult dataclass."""

    def test_image_result_creation(self):
        """Test creating ImageResult with all fields."""
        result = ImageResult(
            id="abc123",
            url_small="https://example.com/small.jpg",
            url_regular="https://example.com/regular.jpg",
            url_full="https://example.com/full.jpg",
            alt_text="Business meeting photo",
            author="John Doe",
            source="unsplash",
            download_url="https://example.com/download",
        )

        assert result.id == "abc123"
        assert result.source == "unsplash"
        assert "small" in result.url_small
        assert "regular" in result.url_regular


class TestImageSearchResult:
    """Tests for ImageSearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating ImageSearchResult."""
        result = ImageSearchResult(
            query="経営管理",
            images=[],
            source_used="unsplash",
        )

        assert result.query == "経営管理"
        assert result.source_used == "unsplash"
        assert len(result.images) == 0

    def test_to_dict(self):
        """Test converting ImageSearchResult to dictionary."""
        image = ImageResult(
            id="test1",
            url_small="https://example.com/s.jpg",
            url_regular="https://example.com/r.jpg",
            url_full="https://example.com/f.jpg",
            alt_text="Test image",
            author="Test Author",
            source="pexels",
            download_url="https://example.com/d.jpg",
        )
        result = ImageSearchResult(
            query="テスト",
            images=[image],
            source_used="pexels",
        )

        d = result.to_dict()

        assert d["query"] == "テスト"
        assert d["source"] == "pexels"
        assert len(d["images"]) == 1
        assert d["images"][0]["id"] == "test1"
        assert d["images"][0]["author"] == "Test Author"


class TestImageService:
    """Tests for ImageService."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.unsplash_access_key = "test_unsplash_key"
        settings.pexels_api_key = "test_pexels_key"
        return settings

    @pytest.fixture
    def mock_unsplash_response(self):
        """Create mock Unsplash API response."""
        return {
            "results": [
                {
                    "id": "unsplash1",
                    "urls": {
                        "small": "https://unsplash.com/s1.jpg",
                        "regular": "https://unsplash.com/r1.jpg",
                        "full": "https://unsplash.com/f1.jpg",
                    },
                    "alt_description": "Business meeting",
                    "user": {"name": "John Photographer"},
                    "links": {"download_location": "https://unsplash.com/dl1"},
                },
                {
                    "id": "unsplash2",
                    "urls": {
                        "small": "https://unsplash.com/s2.jpg",
                        "regular": "https://unsplash.com/r2.jpg",
                        "full": "https://unsplash.com/f2.jpg",
                    },
                    "alt_description": None,
                    "user": {"name": "Jane Photo"},
                    "links": {"download_location": "https://unsplash.com/dl2"},
                },
            ]
        }

    @pytest.fixture
    def mock_pexels_response(self):
        """Create mock Pexels API response."""
        return {
            "photos": [
                {
                    "id": 12345,
                    "src": {
                        "small": "https://pexels.com/s1.jpg",
                        "large": "https://pexels.com/l1.jpg",
                        "original": "https://pexels.com/o1.jpg",
                    },
                    "alt": "Office workspace",
                    "photographer": "Bob Pexels",
                },
            ]
        }

    @patch("src.services.image_service.get_settings")
    def test_is_available_with_unsplash(self, mock_get_settings, mock_settings):
        """Test is_available returns True when Unsplash key is set."""
        mock_get_settings.return_value = mock_settings

        service = ImageService()
        assert service.is_available() is True

    @patch("src.services.image_service.get_settings")
    def test_is_available_no_keys(self, mock_get_settings):
        """Test is_available returns False when no API keys."""
        settings = Mock()
        settings.unsplash_access_key = ""
        settings.pexels_api_key = ""
        mock_get_settings.return_value = settings

        service = ImageService()
        assert service.is_available() is False

    @patch("src.services.image_service.get_settings")
    def test_search_unsplash_success(
        self, mock_get_settings, mock_settings, mock_unsplash_response
    ):
        """Test successful Unsplash search."""
        mock_get_settings.return_value = mock_settings

        with patch.object(ImageService, "_client", create=True) as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = mock_unsplash_response
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response

            service = ImageService()
            service._client = mock_client

            result = service._search_unsplash("経営管理", per_page=5)

            assert result.query == "経営管理"
            assert result.source_used == "unsplash"
            assert len(result.images) == 2
            assert result.images[0].id == "unsplash1"
            assert result.images[0].author == "John Photographer"

    @patch("src.services.image_service.get_settings")
    def test_search_pexels_success(
        self, mock_get_settings, mock_settings, mock_pexels_response
    ):
        """Test successful Pexels search."""
        mock_get_settings.return_value = mock_settings

        with patch.object(ImageService, "_client", create=True) as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = mock_pexels_response
            mock_response.raise_for_status = Mock()
            mock_client.get.return_value = mock_response

            service = ImageService()
            service._client = mock_client

            result = service._search_pexels("ビジネス", per_page=3, locale="ja")

            assert result.query == "ビジネス"
            assert result.source_used == "pexels"
            assert len(result.images) == 1
            assert result.images[0].id == "12345"
            assert result.images[0].author == "Bob Pexels"

    @patch("src.services.image_service.get_settings")
    def test_extract_keywords_from_prompt_title(self, mock_get_settings, mock_settings):
        """Test keyword extraction from prompt with title."""
        mock_get_settings.return_value = mock_settings
        service = ImageService()

        prompt = """### 図解1: 予算管理サイクル
- 目的: PDCAサイクルを可視化
- 形式: フロー図
"""
        keywords = service._extract_keywords_from_prompt(prompt)

        assert keywords == "予算管理サイクル"

    @patch("src.services.image_service.get_settings")
    def test_extract_keywords_from_prompt_purpose(self, mock_get_settings, mock_settings):
        """Test keyword extraction from prompt with purpose only."""
        mock_get_settings.return_value = mock_settings
        service = ImageService()

        prompt = """- 目的: データ分析の重要性を伝える
- 形式: インフォグラフィック
"""
        keywords = service._extract_keywords_from_prompt(prompt)

        assert keywords == "データ分析の重要性を伝える"

    @patch("src.services.image_service.get_settings")
    def test_extract_keywords_fallback(self, mock_get_settings, mock_settings):
        """Test keyword extraction fallback."""
        mock_get_settings.return_value = mock_settings
        service = ImageService()

        prompt = "Some random text about business management"
        keywords = service._extract_keywords_from_prompt(prompt)

        assert keywords == "Some random text about business management"

    @patch("src.services.image_service.get_settings")
    def test_search_images_no_api_configured(self, mock_get_settings):
        """Test search_images returns error when no API configured."""
        settings = Mock()
        settings.unsplash_access_key = ""
        settings.pexels_api_key = ""
        mock_get_settings.return_value = settings

        service = ImageService()
        result = service.search_images("テスト")

        assert result.error_message != ""
        assert len(result.images) == 0

    @patch("src.services.image_service.get_settings")
    def test_search_for_prompts(self, mock_get_settings, mock_settings):
        """Test searching images for multiple prompts."""
        mock_get_settings.return_value = mock_settings

        service = ImageService()

        # Mock the search_images method
        mock_result = ImageSearchResult(
            query="テスト",
            images=[
                ImageResult(
                    id="1",
                    url_small="s.jpg",
                    url_regular="r.jpg",
                    url_full="f.jpg",
                    alt_text="Test",
                    author="Author",
                    source="unsplash",
                    download_url="d.jpg",
                )
            ],
            source_used="unsplash",
        )

        with patch.object(service, "search_images", return_value=mock_result):
            prompts = [
                "### 図解1: テスト図解\n- 目的: テスト",
                "### 図解2: 別の図解\n- 目的: 別のテスト",
            ]

            results = service.search_for_prompts(prompts, images_per_prompt=3)

            assert len(results) == 2
            assert all(isinstance(r, ImageSearchResult) for r in results)


class TestImageServiceTranslation:
    """Tests for Japanese to English translation feature."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with API keys."""
        settings = Mock()
        settings.unsplash_access_key = "test_unsplash_key"
        settings.pexels_api_key = "test_pexels_key"
        settings.openai_api_key = "test_openai_key"
        return settings

    @patch("src.services.image_service.get_settings")
    def test_translate_english_passthrough(self, mock_get_settings, mock_settings):
        """Test that English text is returned as-is."""
        mock_get_settings.return_value = mock_settings
        service = ImageService()

        result = service._translate_to_english("business management")

        assert result == "business management"

    @patch("src.services.image_service.get_openai_client")
    @patch("src.services.image_service.get_settings")
    def test_translate_japanese_to_english(
        self, mock_get_settings, mock_get_openai, mock_settings
    ):
        """Test Japanese to English translation."""
        mock_get_settings.return_value = mock_settings

        # Mock OpenAI response
        mock_openai = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="budget management"))]
        mock_openai.chat.completions.create.return_value = mock_response
        mock_get_openai.return_value = mock_openai

        service = ImageService()
        result = service._translate_to_english("予算管理")

        assert result == "budget management"
        mock_openai.chat.completions.create.assert_called_once()

    @patch("src.services.image_service.get_openai_client")
    @patch("src.services.image_service.get_settings")
    def test_translate_cache_works(
        self, mock_get_settings, mock_get_openai, mock_settings
    ):
        """Test that translation results are cached."""
        mock_get_settings.return_value = mock_settings

        # Mock OpenAI response
        mock_openai = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="data analysis"))]
        mock_openai.chat.completions.create.return_value = mock_response
        mock_get_openai.return_value = mock_openai

        service = ImageService()

        # First call - should hit API
        result1 = service._translate_to_english("データ分析")
        # Second call - should use cache
        result2 = service._translate_to_english("データ分析")

        assert result1 == "data analysis"
        assert result2 == "data analysis"
        # API should only be called once due to caching
        assert mock_openai.chat.completions.create.call_count == 1

    @patch("src.services.image_service.get_settings")
    def test_translate_no_openai_key(self, mock_get_settings):
        """Test fallback when OpenAI key is not configured."""
        settings = Mock()
        settings.unsplash_access_key = "test_key"
        settings.pexels_api_key = ""
        settings.openai_api_key = ""
        mock_get_settings.return_value = settings

        service = ImageService()
        result = service._translate_to_english("経営管理")

        # Should return original text when no OpenAI key
        assert result == "経営管理"

    @patch("src.services.image_service.get_openai_client")
    @patch("src.services.image_service.get_settings")
    def test_translate_api_error_fallback(
        self, mock_get_settings, mock_get_openai, mock_settings
    ):
        """Test fallback when OpenAI API fails."""
        mock_get_settings.return_value = mock_settings

        # Mock OpenAI to raise an exception
        mock_openai = Mock()
        mock_openai.chat.completions.create.side_effect = Exception("API Error")
        mock_get_openai.return_value = mock_openai

        service = ImageService()
        result = service._translate_to_english("予算管理")

        # Should return original text on error
        assert result == "予算管理"

    @patch("src.services.image_service.get_openai_client")
    @patch("src.services.image_service.get_settings")
    def test_search_images_uses_translation(
        self, mock_get_settings, mock_get_openai, mock_settings
    ):
        """Test that search_images translates Japanese queries for Unsplash."""
        mock_get_settings.return_value = mock_settings

        # Mock OpenAI translation
        mock_openai = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="performance evaluation"))]
        mock_openai.chat.completions.create.return_value = mock_response
        mock_get_openai.return_value = mock_openai

        service = ImageService()

        # Mock Unsplash API response
        mock_unsplash_result = ImageSearchResult(
            query="performance evaluation",
            images=[
                ImageResult(
                    id="1",
                    url_small="s.jpg",
                    url_regular="r.jpg",
                    url_full="f.jpg",
                    alt_text="Test",
                    author="Author",
                    source="unsplash",
                    download_url="d.jpg",
                )
            ],
            source_used="unsplash",
        )

        with patch.object(service, "_search_unsplash", return_value=mock_unsplash_result):
            result = service.search_images("業績評価")

            # Original Japanese query should be preserved in result
            assert result.query == "業績評価"
            assert result.source_used == "unsplash"
            assert len(result.images) == 1
