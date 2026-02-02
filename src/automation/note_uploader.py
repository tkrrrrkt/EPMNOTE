"""
EPM Note Engine - Note.com Uploader

Playwright automation for saving drafts to Note.com.
Uses subprocess to run Playwright in a separate process to avoid
asyncio event loop conflicts with Streamlit.
"""

import json
import os
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of an upload operation."""

    success: bool
    error_message: str | None = None
    screenshot_path: str | None = None
    draft_url: str | None = None
    stderr: str | None = None


class NoteUploader:
    """
    Automation for uploading drafts to Note.com.

    Uses Playwright via subprocess to avoid asyncio conflicts with Streamlit.
    """

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        headless: bool = False,  # Changed default to False for debugging
        screenshot_dir: str | None = None,
    ) -> None:
        """
        Initialize the uploader.

        Args:
            email: Note.com email. Defaults to env var NOTE_EMAIL.
            password: Note.com password. Defaults to env var NOTE_PASSWORD.
            headless: Whether to run browser in headless mode.
            screenshot_dir: Directory to save screenshots on failure.
        """
        settings = get_settings()

        self.email = email or settings.note_email
        self.password = password or settings.note_password
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir or "data/screenshots")

        if not self.email or not self.password:
            raise ValueError(
                "Note.com credentials not configured. "
                "Set NOTE_EMAIL and NOTE_PASSWORD in .env"
            )

        # Ensure screenshot directory exists
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Path to the playwright runner script
        self._runner_script = Path(__file__).parent / "playwright_runner.py"

    def _run_playwright_command(self, command_data: dict, timeout: int = 120) -> UploadResult:
        """
        Run a Playwright command in a subprocess.

        Args:
            command_data: JSON-serializable command data.
            timeout: Timeout in seconds.

        Returns:
            UploadResult from the subprocess.
        """
        try:
            # Run the playwright_runner.py script as a subprocess
            result = subprocess.run(
                [sys.executable, str(self._runner_script)],
                input=json.dumps(command_data, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={**dict(**os.environ), "PYTHONIOENCODING": "utf-8"},
                timeout=timeout,
                cwd=str(Path(__file__).parent.parent.parent),  # Project root
            )
            stderr_output = result.stderr.strip() if result.stderr else None

            if result.returncode != 0:
                logger.error(f"Playwright subprocess failed: {result.stderr}")
                return UploadResult(
                    success=False,
                    error_message=f"プロセスエラー: {result.stderr[:500] if result.stderr else 'Unknown error'}",
                    stderr=stderr_output,
                )

            # Parse JSON output
            try:
                output = json.loads(result.stdout)
                return UploadResult(
                    success=output.get("success", False),
                    error_message=output.get("error_message"),
                    screenshot_path=output.get("screenshot_path"),
                    draft_url=output.get("draft_url"),
                    stderr=stderr_output,
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse subprocess output: {result.stdout}")
                return UploadResult(
                    success=False,
                    error_message=f"出力解析エラー: {e}",
                    stderr=stderr_output,
                )

        except subprocess.TimeoutExpired:
            return UploadResult(
                success=False,
                error_message="操作がタイムアウトしました（120秒）",
            )
        except Exception as e:
            logger.error(f"Subprocess execution failed: {e}")
            return UploadResult(
                success=False,
                error_message=f"実行エラー: {e}",
            )

    def upload_draft(
        self,
        title: str,
        content_md: str,
    ) -> UploadResult:
        """
        Upload an article as a draft to Note.com.

        Args:
            title: Article title.
            content_md: Article content in Markdown format.

        Returns:
            UploadResult with success status and any error details.
        """
        logger.info(f"Starting upload: {title[:50]}...")

        command_data = {
            "command": "upload",
            "email": self.email,
            "password": self.password,
            "title": title,
            "content": content_md,
            "headless": self.headless,
            "screenshot_dir": str(self.screenshot_dir),
        }

        return self._run_playwright_command(command_data, timeout=300)  # 5 minutes for debugging

    def test_login(self) -> UploadResult:
        """
        Test login credentials without uploading.

        Returns:
            UploadResult indicating if login was successful.
        """
        logger.info("Testing login...")

        command_data = {
            "command": "test_login",
            "email": self.email,
            "password": self.password,
            "headless": self.headless,
            "screenshot_dir": str(self.screenshot_dir),
        }

        return self._run_playwright_command(command_data, timeout=180)  # 3 minutes for debugging
