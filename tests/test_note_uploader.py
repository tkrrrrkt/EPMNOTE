"""
Unit tests for EPM Note Engine NoteUploader.

Tests subprocess-based Playwright automation with mocked subprocess calls.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.automation.note_uploader import NoteUploader, UploadResult


# ============================================================================
# UploadResult Tests
# ============================================================================

class TestUploadResult:
    """Tests for UploadResult dataclass."""

    def test_success_result(self):
        """Test successful upload result."""
        result = UploadResult(
            success=True,
            draft_url="https://note.com/drafts/123",
        )

        assert result.success is True
        assert result.error_message is None
        assert result.draft_url == "https://note.com/drafts/123"

    def test_failure_result(self):
        """Test failed upload result."""
        result = UploadResult(
            success=False,
            error_message="ログインに失敗しました",
            screenshot_path="/path/to/screenshot.png",
        )

        assert result.success is False
        assert "ログイン" in result.error_message
        assert result.screenshot_path is not None


# ============================================================================
# NoteUploader Initialization Tests
# ============================================================================

class TestNoteUploaderInit:
    """Tests for NoteUploader initialization."""

    @patch("src.automation.note_uploader.get_settings")
    def test_init_with_env_credentials(self, mock_settings):
        """Test initialization with environment credentials."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        uploader = NoteUploader()

        assert uploader.email == "test@example.com"
        assert uploader.password == "testpass"
        assert uploader.headless is True

    @patch("src.automation.note_uploader.get_settings")
    def test_init_with_explicit_credentials(self, mock_settings):
        """Test initialization with explicit credentials."""
        mock_settings.return_value = Mock(
            note_email="default@example.com",
            note_password="defaultpass",
        )

        uploader = NoteUploader(
            email="explicit@example.com",
            password="explicitpass",
            headless=False,
        )

        assert uploader.email == "explicit@example.com"
        assert uploader.password == "explicitpass"
        assert uploader.headless is False

    @patch("src.automation.note_uploader.get_settings")
    def test_init_missing_credentials(self, mock_settings):
        """Test initialization fails with missing credentials."""
        mock_settings.return_value = Mock(
            note_email="",
            note_password="",
        )

        with pytest.raises(ValueError) as exc_info:
            NoteUploader()

        assert "credentials" in str(exc_info.value).lower()

    @patch("src.automation.note_uploader.get_settings")
    def test_screenshot_directory_creation(self, mock_settings, tmp_path):
        """Test screenshot directory is created."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        screenshot_dir = tmp_path / "screenshots"
        uploader = NoteUploader(screenshot_dir=str(screenshot_dir))

        assert screenshot_dir.exists()


# ============================================================================
# Upload Draft Tests (Subprocess-based)
# ============================================================================

class TestNoteUploaderUpload:
    """Tests for upload_draft functionality using subprocess."""

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_upload_draft_success(self, mock_settings, mock_subprocess_run):
        """Test successful upload via subprocess."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock successful subprocess response
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "draft_url": "https://note.com/drafts/123",
            }),
            stderr="",
        )

        uploader = NoteUploader()
        result = uploader.upload_draft(
            title="テスト記事",
            content_md="# 記事内容\n\nテスト",
        )

        assert result.success is True
        assert result.draft_url == "https://note.com/drafts/123"
        mock_subprocess_run.assert_called_once()

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_upload_draft_login_failure(self, mock_settings, mock_subprocess_run):
        """Test upload fails on login failure."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock failed login response
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                "success": False,
                "error_message": "ログインに失敗しました。認証情報を確認してください。",
                "screenshot_path": "/path/to/error.png",
            }),
            stderr="",
        )

        uploader = NoteUploader()
        result = uploader.upload_draft(
            title="テスト記事",
            content_md="# 記事内容",
        )

        assert result.success is False
        assert "ログイン" in result.error_message

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_upload_draft_subprocess_error(self, mock_settings, mock_subprocess_run):
        """Test upload handles subprocess error."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock subprocess failure
        mock_subprocess_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Some error occurred",
        )

        uploader = NoteUploader()
        result = uploader.upload_draft(
            title="テスト記事",
            content_md="# 記事内容",
        )

        assert result.success is False
        assert "プロセスエラー" in result.error_message

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_upload_draft_timeout(self, mock_settings, mock_subprocess_run):
        """Test upload handles timeout."""
        import subprocess

        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock timeout
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=120)

        uploader = NoteUploader()
        result = uploader.upload_draft(
            title="テスト記事",
            content_md="# 記事内容",
        )

        assert result.success is False
        assert "タイムアウト" in result.error_message

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_upload_draft_json_parse_error(self, mock_settings, mock_subprocess_run):
        """Test upload handles invalid JSON response."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock invalid JSON output
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="invalid json",
            stderr="",
        )

        uploader = NoteUploader()
        result = uploader.upload_draft(
            title="テスト記事",
            content_md="# 記事内容",
        )

        assert result.success is False
        assert "出力解析エラー" in result.error_message


# ============================================================================
# Test Login Tests (Subprocess-based)
# ============================================================================

class TestNoteUploaderTestLogin:
    """Tests for test_login functionality using subprocess."""

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_test_login_success(self, mock_settings, mock_subprocess_run):
        """Test successful login test via subprocess."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock successful subprocess response
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
            }),
            stderr="",
        )

        uploader = NoteUploader()
        result = uploader.test_login()

        assert result.success is True
        mock_subprocess_run.assert_called_once()

    @patch("src.automation.note_uploader.subprocess.run")
    @patch("src.automation.note_uploader.get_settings")
    def test_test_login_failure(self, mock_settings, mock_subprocess_run):
        """Test failed login test via subprocess."""
        mock_settings.return_value = Mock(
            note_email="test@example.com",
            note_password="testpass",
        )

        # Mock failed login response
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                "success": False,
                "error_message": "ログインに失敗しました。認証情報を確認してください。",
            }),
            stderr="",
        )

        uploader = NoteUploader()
        result = uploader.test_login()

        assert result.success is False
        assert "ログイン" in result.error_message


# ============================================================================
# Playwright Runner Tests (Direct execution tests)
# ============================================================================

class TestPlaywrightRunner:
    """Tests for playwright_runner.py script."""

    def test_runner_script_exists(self):
        """Test that playwright_runner.py exists."""
        from pathlib import Path
        runner_path = Path(__file__).parent.parent / "src" / "automation" / "playwright_runner.py"
        assert runner_path.exists(), f"playwright_runner.py not found at {runner_path}"

    def test_runner_script_syntax(self):
        """Test that playwright_runner.py has valid Python syntax."""
        import py_compile
        from pathlib import Path
        runner_path = Path(__file__).parent.parent / "src" / "automation" / "playwright_runner.py"
        # This will raise SyntaxError if the file has invalid syntax
        py_compile.compile(str(runner_path), doraise=True)
