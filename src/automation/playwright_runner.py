"""
Standalone Playwright runner script.

This script runs in a separate process to avoid asyncio event loop conflicts
with Streamlit. Uses async_playwright with ProactorEventLoop on Windows
(required for subprocess support).
"""

import asyncio
import html
import json
import re
import sys
import time
from pathlib import Path

# On Windows, use ProactorEventLoop which supports subprocess
# (SelectorEventLoop does NOT support subprocess on Windows)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


# Note.com URLs
LOGIN_URL = "https://note.com/login"
NEW_POST_URL = "https://note.com/new"

# Selectors - Note.com specific
SELECTORS = {
    # Login page
    "email_input": 'input[placeholder*="mail"], input[placeholder*="note ID"], input[type="email"], input[autocomplete="username"], input[autocomplete="email"], input[name*="email"], input[name*="user"], input[name*="login"], input[type="text"]',
    "password_input": 'input[type="password"], input[autocomplete="current-password"], input[name*="password"]',
    "login_button": 'button:has-text("ログイン"), button:has-text("ログインする"), button[type="submit"]',

    # New post page - multiple fallback selectors
    "title_input": '[data-testid="title-input"], input[placeholder*="タイトル"], textarea[placeholder*="タイトル"], [contenteditable="true"][data-placeholder*="タイトル"], .note-title input, .note-title textarea, h1[contenteditable="true"], [role="textbox"][aria-label*="タイトル"]',
    "content_editor": '[data-testid="editor"], div[contenteditable="true"].ProseMirror, div[contenteditable="true"], .note-body [contenteditable="true"], textarea.editor, [role="textbox"]',
    "draft_save_button": 'button:has-text("下書き保存"), button:has-text("保存"), [data-testid="save-draft"]',

    # Success indicators
    "draft_saved_toast": 'text="下書きを保存しました", text="保存しました", [role="alert"]',
}

NAVIGATION_TIMEOUT = 60000  # 60 seconds for navigation
ACTION_TIMEOUT = 30000  # 30 seconds for actions (was 10s)

# Fallback selectors for onboarding/template selection screens
START_WRITE_SELECTORS = [
    'button:has-text("空白で作成")',
    'a:has-text("空白で作成")',
    'button:has-text("空白")',
    'a:has-text("空白")',
    'button:has-text("新規作成")',
    'a:has-text("新規作成")',
    'button:has-text("新規投稿")',
    'a:has-text("新規投稿")',
    'button:has-text("記事を書く")',
    'a:has-text("記事を書く")',
    'button:has-text("投稿する")',
    'a:has-text("投稿する")',
    'button:has-text("書く")',
    'a:has-text("書く")',
    'text="はじめる"',
]


async def _try_click_start_writing(page) -> bool:
    """Try to click a button/link to start a blank post."""
    for selector in START_WRITE_SELECTORS:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0 and await locator.is_visible():
                await locator.click()
                return True
        except Exception:
            continue
    return False


async def _first_visible(page, selectors: list[str], timeout: int):
    """Return the first visible locator from a list of selectors."""
    last_error = None
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as e:
            last_error = e
            continue
    raise last_error if last_error else PlaywrightTimeout("No visible selector found")


async def _first_visible_locator(locators: list, timeout: int):
    """Return the first visible locator from a list of locators."""
    last_error = None
    for locator in locators:
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception as e:
            last_error = e
            continue
    raise last_error if last_error else PlaywrightTimeout("No visible locator found")


async def _wait_until_enabled(locator, timeout_ms: int) -> bool:
    """Wait until a locator is visible and enabled."""
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        try:
            if await locator.is_visible() and await locator.is_enabled():
                return True
        except Exception:
            pass
        await asyncio.sleep(0.2)
    return False


async def _input_value(locator) -> str:
    """Safely get input value if possible."""
    try:
        return await locator.input_value()
    except Exception:
        return ""


async def _detect_captcha(page) -> bool:
    """Detect common captcha widgets."""
    try:
        captcha = page.locator(
            'iframe[src*="captcha"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], div.g-recaptcha, div.hcaptcha'
        )
        return await captcha.count() > 0
    except Exception:
        return False


async def _find_login_form(page):
    """Find the login form area."""
    candidates = [
        page.locator('form:has(input[type="password"])'),
        page.locator('form:has-text("ログイン")'),
    ]
    for cand in candidates:
        try:
            if await cand.count() > 0:
                form = cand.first
                await form.wait_for(state="visible", timeout=ACTION_TIMEOUT)
                return form
        except Exception:
            continue
    return page.locator("body")


async def _locate_editor_elements(page, timeout: int):
    """Locate title input and content editor elements."""
    # Prefer contenteditable elements
    try:
        await page.wait_for_selector('[contenteditable="true"]', timeout=timeout, state="visible")
        editables = await page.locator('[contenteditable="true"]').all()
        if len(editables) >= 2:
            return editables[0], editables[1], False
        if len(editables) == 1:
            title_input = page.locator(SELECTORS["title_input"]).first
            if await title_input.count() > 0:
                return title_input, editables[0], False
            # Fallback: single editor for both title and body
            return editables[0], editables[0], True
    except PlaywrightTimeout:
        pass

    # Fallback to selectors
    title_input = page.locator(SELECTORS["title_input"]).first
    content_editor = page.locator(SELECTORS["content_editor"]).first
    await title_input.wait_for(state="visible", timeout=timeout)
    await content_editor.wait_for(state="visible", timeout=timeout)
    return title_input, content_editor, False


async def _ensure_editor_ready(page):
    """Ensure editor is ready, handling template/onboarding screens if needed."""
    try:
        return await _locate_editor_elements(page, ACTION_TIMEOUT)
    except PlaywrightTimeout:
        # Try to click through any template/onboarding screen
        clicked = await _try_click_start_writing(page)
        if clicked:
            try:
                await page.wait_for_load_state("domcontentloaded")
            except PlaywrightTimeout:
                pass
        # Try again with longer timeout
        return await _locate_editor_elements(page, NAVIGATION_TIMEOUT)


async def _set_text(page, locator, text: str) -> None:
    """Set text into an input/editor with a robust fallback."""
    try:
        await locator.fill(text)
        if await _input_value(locator) == text:
            return
    except Exception:
        pass

    await locator.click()
    shortcut = "Meta+A" if sys.platform == "darwin" else "Control+A"
    try:
        await page.keyboard.press(shortcut)
        await page.keyboard.press("Delete")
    except Exception:
        pass
    await page.keyboard.insert_text(text)
    if await _input_value(locator) == text:
        return
    # Final fallback: set value via JS and dispatch events
    try:
        await locator.evaluate(
            """(el, val) => {
                el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            text,
        )
    except Exception:
        pass


def _format_inline(text: str) -> str:
    """Basic inline markdown to HTML (bold/italic/code)."""
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def _markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML. Uses markdown lib if available, else fallback."""
    try:
        import markdown as md  # type: ignore
        return md.markdown(markdown_text, extensions=["extra", "sane_lists"])
    except Exception:
        pass

    lines = markdown_text.splitlines()
    html_lines: list[str] = []
    in_ul = False
    in_ol = False

    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            continue

        if stripped.startswith("### "):
            html_lines.append(f"<h3>{_format_inline(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{_format_inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{_format_inline(stripped[2:])}</h1>")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_format_inline(stripped[2:])}</li>")
            continue

        ordered_match = re.match(r"\d+\.\s+(.+)", stripped)
        if ordered_match:
            if not in_ol:
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{_format_inline(ordered_match.group(1))}</li>")
            continue

        html_lines.append(f"<p>{_format_inline(stripped)}</p>")

    if in_ul:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "\n".join(html_lines)


async def _set_rich_text(locator, html_content: str) -> None:
    """Insert HTML into a contenteditable editor."""
    try:
        await locator.evaluate(
            """(el, html) => {
                el.focus();
                el.innerHTML = "";
                el.insertAdjacentHTML("beforeend", html);
                el.dispatchEvent(new Event("input", { bubbles: true }));
            }""",
            html_content,
        )
    except Exception:
        # Fallback to plain text if HTML insert fails
        await locator.evaluate(
            """(el, text) => {
                el.focus();
                el.innerText = text;
                el.dispatchEvent(new Event("input", { bubbles: true }));
            }""",
            html_content,
        )


async def run_upload_async(email: str, password: str, title: str, content: str, headless: bool = True, screenshot_dir: str = "data/screenshots"):
    """Run the upload process asynchronously."""
    screenshot_path = None

    async with async_playwright() as p:
        browser = None
        try:
            # Launch browser with settings to avoid detection
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            # Create context that looks like a real browser
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="ja-JP",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                java_script_enabled=True,
            )

            # Remove webdriver property to avoid detection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            page = await context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

            # Step 1: Login
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
            form = await _find_login_form(page)
            email_input = await _first_visible_locator(
                [
                    form.get_by_label("メールアドレス または note ID"),
                    form.get_by_placeholder("mail@example.com or note ID"),
                    form.get_by_placeholder("メールアドレス"),
                    form.locator(SELECTORS["email_input"]).first,
                ],
                ACTION_TIMEOUT,
            )
            password_input = await _first_visible_locator(
                [
                    form.get_by_label("パスワード"),
                    form.get_by_placeholder("パスワード"),
                    form.locator(SELECTORS["password_input"]).first,
                ],
                ACTION_TIMEOUT,
            )

            await _set_text(page, email_input, email)
            await _set_text(page, password_input, password)

            # Verify values (some UIs require input events to enable button)
            email_value = await _input_value(email_input)
            password_value = await _input_value(password_input)
            print(f"DEBUG: email length={len(email_value)} password length={len(password_value)}", file=sys.stderr)

            login_button = await _first_visible_locator(
                [
                    form.get_by_role("button", name="ログイン"),
                    form.locator(SELECTORS["login_button"]).first,
                    form.locator('button[type="submit"]').first,
                ],
                ACTION_TIMEOUT,
            )

            if not await _wait_until_enabled(login_button, 10000):
                # Try blur/enter to trigger validation
                try:
                    await password_input.press("Tab")
                except Exception:
                    pass
                if not await _wait_until_enabled(login_button, 5000):
                    try:
                        await password_input.press("Enter")
                    except Exception:
                        pass
                if not await _wait_until_enabled(login_button, 5000):
                    if await _detect_captcha(page):
                        await page.screenshot(path=str(Path(screenshot_dir) / "debug_login_captcha.png"))
                        raise PlaywrightTimeout("CAPTCHAが検出され、ログインがブロックされました")
                    await page.screenshot(path=str(Path(screenshot_dir) / "debug_login_disabled.png"))
                    raise PlaywrightTimeout("ログインボタンが有効化されませんでした")

            await login_button.click()

            try:
                await page.wait_for_url(lambda url: "login" not in url, timeout=NAVIGATION_TIMEOUT)
            except PlaywrightTimeout as e:
                raise PlaywrightTimeout("ログイン後の遷移を確認できませんでした") from e

            # Step 2: Navigate to new post
            await page.goto(NEW_POST_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)

            # Wait for loading spinner to disappear (Note.com shows a loading animation)
            # The spinner is typically a div with dots or similar
            try:
                # Wait for any loading indicator to disappear
                await page.wait_for_function(
                    """() => {
                        // Check if page has finished loading (no loading spinners)
                        const body = document.body;
                        const text = body ? body.innerText : '';
                        // Page should have some substantial content
                        return text.length > 100;
                    }""",
                    timeout=60000
                )
            except PlaywrightTimeout:
                print("DEBUG: Page content check timed out", file=sys.stderr)

            # Wait a bit more for any JavaScript to finish
            await page.wait_for_timeout(5000)

            # Debug: Save screenshot to see what page we're on
            debug_path = Path(screenshot_dir) / "debug_after_navigation.png"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(debug_path))

            # Get current URL for debugging
            current_url = page.url
            print(f"DEBUG: Current URL after navigation: {current_url}", file=sys.stderr)

            # Get page HTML for debugging
            page_title = await page.title()
            print(f"DEBUG: Page title: {page_title}", file=sys.stderr)

            # Step 3: Ensure editor is ready (handle template/onboarding screens)
            try:
                title_input, content_editor, same_editor = await _ensure_editor_ready(page)
            except PlaywrightTimeout:
                # Take another screenshot before failing
                await page.screenshot(path=str(Path(screenshot_dir) / "debug_no_editor_found.png"))
                raise

            # Step 4: Enter title/content (use fast input)
            content_html = _markdown_to_html(content)
            if same_editor:
                combined_html = f"<h1>{html.escape(title)}</h1>\n{content_html}"
                await _set_rich_text(content_editor, combined_html)
            else:
                await _set_text(page, title_input, title)
                await _set_rich_text(content_editor, content_html)
            await page.wait_for_timeout(500)

            # Debug screenshot after content entry
            await page.screenshot(path=str(Path(screenshot_dir) / "debug_after_content.png"))

            # Step 5: Save draft
            save_button = page.locator(SELECTORS["draft_save_button"]).first
            await save_button.wait_for(state="visible", timeout=ACTION_TIMEOUT)
            await save_button.click()

            try:
                await page.wait_for_selector(SELECTORS["draft_saved_toast"], timeout=ACTION_TIMEOUT)
            except PlaywrightTimeout:
                # Check if URL suggests success
                if "draft" not in page.url.lower() and "edit" not in page.url.lower():
                    raise PlaywrightTimeout("Save confirmation not detected")

            return {
                "success": True,
                "draft_url": page.url,
            }

        except PlaywrightTimeout as e:
            screenshot_path = await _save_screenshot_async(page if 'page' in dir() else None, screenshot_dir)
            return {
                "success": False,
                "error_message": f"操作がタイムアウトしました: {e}",
                "screenshot_path": screenshot_path,
            }
        except Exception as e:
            screenshot_path = await _save_screenshot_async(page if 'page' in dir() else None, screenshot_dir)
            return {
                "success": False,
                "error_message": f"アップロードに失敗しました: {e}",
                "screenshot_path": screenshot_path,
            }
        finally:
            if browser:
                await browser.close()


async def run_test_login_async(email: str, password: str, headless: bool = True, screenshot_dir: str = "data/screenshots"):
    """Test login only asynchronously."""
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT)
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
            form = await _find_login_form(page)
            email_input = await _first_visible_locator(
                [
                    form.get_by_label("メールアドレス または note ID"),
                    form.get_by_placeholder("mail@example.com or note ID"),
                    form.get_by_placeholder("メールアドレス"),
                    form.locator(SELECTORS["email_input"]).first,
                ],
                ACTION_TIMEOUT,
            )
            password_input = await _first_visible_locator(
                [
                    form.get_by_label("パスワード"),
                    form.get_by_placeholder("パスワード"),
                    form.locator(SELECTORS["password_input"]).first,
                ],
                ACTION_TIMEOUT,
            )

            await _set_text(page, email_input, email)
            await _set_text(page, password_input, password)

            login_button = await _first_visible_locator(
                [
                    form.get_by_role("button", name="ログイン"),
                    form.locator(SELECTORS["login_button"]).first,
                    form.locator('button[type="submit"]').first,
                ],
                ACTION_TIMEOUT,
            )

            if not await _wait_until_enabled(login_button, 10000):
                try:
                    await password_input.press("Tab")
                except Exception:
                    pass
                if not await _wait_until_enabled(login_button, 5000):
                    try:
                        await password_input.press("Enter")
                    except Exception:
                        pass
                if not await _wait_until_enabled(login_button, 5000):
                    if await _detect_captcha(page):
                        await page.screenshot(path=str(Path(screenshot_dir) / "debug_login_captcha.png"))
                        raise PlaywrightTimeout("CAPTCHAが検出され、ログインがブロックされました")
                    await page.screenshot(path=str(Path(screenshot_dir) / "debug_login_disabled.png"))
                    raise PlaywrightTimeout("ログインボタンが有効化されませんでした")

            await login_button.click()

            await page.wait_for_url(lambda url: "login" not in url, timeout=NAVIGATION_TIMEOUT)

            return {"success": True}

        except PlaywrightTimeout:
            screenshot_path = await _save_screenshot_async(page if 'page' in dir() else None, screenshot_dir)
            return {
                "success": False,
                "error_message": "ログインに失敗しました。認証情報を確認してください。",
                "screenshot_path": screenshot_path,
            }
        finally:
            if browser:
                await browser.close()


async def _save_screenshot_async(page, screenshot_dir: str) -> str | None:
    """Save error screenshot asynchronously."""
    if page is None:
        return None
    try:
        from datetime import datetime
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(screenshot_dir) / f"error_{timestamp}.png"
        await page.screenshot(path=str(path))
        return str(path)
    except:
        return None


def run_upload(email: str, password: str, title: str, content: str, headless: bool = True, screenshot_dir: str = "data/screenshots"):
    """Synchronous wrapper for run_upload_async."""
    # Use ProactorEventLoop on Windows (supports subprocess)
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_upload_async(email, password, title, content, headless, screenshot_dir))
    finally:
        loop.close()


def run_test_login(email: str, password: str, headless: bool = True, screenshot_dir: str = "data/screenshots"):
    """Synchronous wrapper for run_test_login_async."""
    # Use ProactorEventLoop on Windows (supports subprocess)
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_test_login_async(email, password, headless, screenshot_dir))
    finally:
        loop.close()


if __name__ == "__main__":
    # Read command from stdin as JSON
    input_data = json.loads(sys.stdin.read())

    command = input_data.get("command")

    if command == "upload":
        result = run_upload(
            email=input_data["email"],
            password=input_data["password"],
            title=input_data["title"],
            content=input_data["content"],
            headless=input_data.get("headless", True),
            screenshot_dir=input_data.get("screenshot_dir", "data/screenshots"),
        )
    elif command == "test_login":
        result = run_test_login(
            email=input_data["email"],
            password=input_data["password"],
            headless=input_data.get("headless", True),
            screenshot_dir=input_data.get("screenshot_dir", "data/screenshots"),
        )
    else:
        result = {"success": False, "error_message": f"Unknown command: {command}"}

    # Output result as JSON
    print(json.dumps(result, ensure_ascii=False))
