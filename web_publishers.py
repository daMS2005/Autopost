import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from video_splitter import load_post_metadata_for_video

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BROWSER_PROFILE_DIR = PROJECT_ROOT / "data" / "browser_profiles"
YOUTUBE_PROFILE_DIR = DEFAULT_BROWSER_PROFILE_DIR / "youtube"
TIKTOK_PROFILE_DIR = DEFAULT_BROWSER_PROFILE_DIR / "tiktok"
INSTAGRAM_PROFILE_DIR = DEFAULT_BROWSER_PROFILE_DIR / "instagram"

YOUTUBE_STUDIO_URL = "https://studio.youtube.com"
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/upload?lang=en"
TIKTOK_EMAIL_LOGIN_URL = "https://www.tiktok.com/login/phone-or-email/email"
INSTAGRAM_HOME_URL = "https://www.instagram.com/"
INSTAGRAM_LOGIN_URL = "https://www.instagram.com/accounts/login/"
INSTAGRAM_CREATE_URL = "https://www.instagram.com/"
INSTAGRAM_DEBUG_DIR = PROJECT_ROOT / "output" / "debug" / "instagram"


def load_manifest(manifest_path):
    return json.loads(Path(manifest_path).expanduser().resolve().read_text(encoding="utf-8"))


def get_manifest_part(manifest, part_number):
    for part in manifest.get("parts", []):
        if int(part.get("part_number", 0)) == int(part_number):
            return part
    raise RuntimeError(f"Part {part_number} was not found in the manifest.")


def infer_publish_inputs(video_path, *, title=None, category=None, subreddit=None):
    metadata = load_post_metadata_for_video(video_path) or {}
    return {
        "title": title or metadata.get("title"),
        "category": category or metadata.get("category"),
        "subreddit": subreddit or metadata.get("subreddit"),
    }


class BrowserPublisher:
    def __init__(self, profile_dir, *, headless=False, slow_mo_ms=0):
        self.profile_dir = Path(profile_dir).expanduser().resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.slow_mo_ms = int(slow_mo_ms or 0)
        self._playwright = None
        self._context = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        crash_dir = PROJECT_ROOT / "data" / "browser_profiles" / "crashpad"
        crash_dir.mkdir(parents=True, exist_ok=True)
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
            viewport={"width": 1440, "height": 1000},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-crash-reporter",
                "--disable-crashpad",
                f"--crash-dumps-dir={crash_dir}",
            ],
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("Browser context is not open.")
        return self._page

    def wait_for_url_fragment(self, fragment, timeout_ms=120000):
        self.page.wait_for_function(
            "(fragment) => window.location.href.includes(fragment)",
            fragment,
            timeout=timeout_ms,
        )

    def wait_for_any_selector(self, selectors, timeout_ms=60000):
        deadline = time.time() + (timeout_ms / 1000)
        last_error = None
        while time.time() < deadline:
            for selector in selectors:
                try:
                    locator = self.page.locator(selector).first
                    if locator.is_visible(timeout=500):
                        return locator
                except Exception as exc:
                    last_error = exc
            time.sleep(0.5)
        if last_error:
            raise last_error
        raise RuntimeError(f"None of the selectors became visible: {selectors}")


class YouTubeWebPublisher(BrowserPublisher):
    def __init__(self, *, headless=False, slow_mo_ms=0):
        super().__init__(YOUTUBE_PROFILE_DIR, headless=headless, slow_mo_ms=slow_mo_ms)
        self.email = os.getenv("YOUTUBE_LOGIN_EMAIL") or os.getenv("GOOGLE_LOGIN_EMAIL")
        self.password = os.getenv("YOUTUBE_LOGIN_PASSWORD") or os.getenv("GOOGLE_LOGIN_PASSWORD")

    def ensure_logged_in(self):
        page = self.page
        page.goto(YOUTUBE_STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        if "accounts.google.com" not in page.url:
            return

        if self.email:
            email_input = self.wait_for_any_selector(
                ["input[type='email']", "input[name='identifier']"],
                timeout_ms=30000,
            )
            email_input.fill(self.email)
            self.wait_for_any_selector(["#identifierNext button", "#identifierNext"]).click()
            page.wait_for_load_state("networkidle")

        if self.password:
            password_input = self.wait_for_any_selector(
                ["input[type='password']", "input[name='Passwd']"],
                timeout_ms=30000,
            )
            password_input.fill(self.password)
            self.wait_for_any_selector(["#passwordNext button", "#passwordNext"]).click()

        try:
            self.wait_for_url_fragment("studio.youtube.com", timeout_ms=120000)
        except Exception as exc:
            raise RuntimeError(
                "YouTube login did not complete automatically. This often means Google requested a captcha or 2FA challenge."
            ) from exc

    def upload_video(self, video_path, *, title, description="", privacy_status="PRIVATE"):
        page = self.page
        self.ensure_logged_in()
        page.goto(YOUTUBE_STUDIO_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        create_button = self.wait_for_any_selector(
            [
                "button[aria-label='Create']",
                "ytcp-button#create-icon",
                "button:has-text('Create')",
            ],
            timeout_ms=60000,
        )
        create_button.click()
        upload_button = self.wait_for_any_selector(
            [
                "tp-yt-paper-item:has-text('Upload videos')",
                "text=Upload videos",
            ],
            timeout_ms=30000,
        )
        upload_button.click()

        file_input = self.wait_for_any_selector(["input[type='file']"], timeout_ms=30000)
        file_input.set_input_files(str(Path(video_path).expanduser().resolve()))

        textboxes = page.locator("div[role='textbox']").all()
        if len(textboxes) >= 1:
            textboxes[0].click()
            textboxes[0].fill(title)
        if len(textboxes) >= 2:
            textboxes[1].click()
            textboxes[1].fill(description)

        for _ in range(3):
            next_button = self.wait_for_any_selector(
                [
                    "button[aria-label='Next']",
                    "ytcp-button:has-text('Next')",
                    "button:has-text('Next')",
                ],
                timeout_ms=30000,
            )
            next_button.click()
            page.wait_for_load_state("networkidle")

        visibility_selector = {
            "PRIVATE": "tp-yt-paper-radio-button[name='PRIVATE']",
            "UNLISTED": "tp-yt-paper-radio-button[name='UNLISTED']",
            "PUBLIC": "tp-yt-paper-radio-button[name='PUBLIC']",
        }.get(str(privacy_status).strip().upper(), "tp-yt-paper-radio-button[name='PRIVATE']")
        self.wait_for_any_selector([visibility_selector], timeout_ms=30000).click()

        done_button = self.wait_for_any_selector(
            [
                "ytcp-button:has-text('Done')",
                "button:has-text('Done')",
            ],
            timeout_ms=30000,
        )
        done_button.click()
        page.wait_for_load_state("networkidle")
        return {
            "status": "submitted",
            "platform": "youtube",
            "video_path": str(Path(video_path).expanduser().resolve()),
            "title": title,
        }


class TikTokWebPublisher(BrowserPublisher):
    def __init__(self, *, headless=False, slow_mo_ms=0):
        super().__init__(TIKTOK_PROFILE_DIR, headless=headless, slow_mo_ms=slow_mo_ms)
        self.identifier = (
            os.getenv("TIKTOK_LOGIN_EMAIL")
            or os.getenv("TIKTOK_LOGIN_USERNAME")
            or os.getenv("TIKTOK_LOGIN_PHONE")
        )
        self.password = os.getenv("TIKTOK_LOGIN_PASSWORD")

    def ensure_logged_in(self):
        page = self.page
        page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        if "/login" not in page.url and not page.locator("text=Log in").first.is_visible(
            timeout=1000
        ):
            return

        page.goto(TIKTOK_EMAIL_LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        if self.identifier:
            self.wait_for_any_selector(
                [
                    "input[name='username']",
                    "input[placeholder*='Email']",
                    "input[type='text']",
                ],
                timeout_ms=30000,
            ).fill(self.identifier)
        if self.password:
            self.wait_for_any_selector(
                [
                    "input[type='password']",
                    "input[name='password']",
                ],
                timeout_ms=30000,
            ).fill(self.password)
            self.wait_for_any_selector(
                [
                    "button[type='submit']",
                    "button:has-text('Log in')",
                ],
                timeout_ms=30000,
            ).click()

        try:
            self.wait_for_url_fragment("/upload", timeout_ms=120000)
        except Exception as exc:
            raise RuntimeError(
                "TikTok login did not complete automatically. TikTok often requires an anti-bot challenge or extra verification."
            ) from exc

    def upload_video(self, video_path, *, caption):
        page = self.page
        self.ensure_logged_in()
        page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        file_input = self.wait_for_any_selector(["input[type='file']"], timeout_ms=60000)
        file_input.set_input_files(str(Path(video_path).expanduser().resolve()))

        caption_box = self.wait_for_any_selector(
            [
                "div[contenteditable='true']",
                "div[role='textbox']",
                "textarea",
            ],
            timeout_ms=120000,
        )
        caption_box.click()
        try:
            caption_box.fill(caption)
        except Exception:
            page.keyboard.insert_text(caption)

        post_button = self.wait_for_any_selector(
            [
                "button:has-text('Post')",
                "button[data-e2e='post_video_button']",
            ],
            timeout_ms=120000,
        )
        post_button.click()
        page.wait_for_load_state("networkidle")
        return {
            "status": "submitted",
            "platform": "tiktok",
            "video_path": str(Path(video_path).expanduser().resolve()),
            "caption": caption,
        }


class InstagramWebPublisher(BrowserPublisher):
    def __init__(self, *, headless=False, slow_mo_ms=0):
        super().__init__(INSTAGRAM_PROFILE_DIR, headless=headless, slow_mo_ms=slow_mo_ms)
        self.username = os.getenv("INSTAGRAM_USERNAME")
        self.password = os.getenv("INSTAGRAM_PASSWORD")

    def ensure_logged_in(self):
        page = self.page
        print("[Instagram] Opening Instagram...", flush=True)
        self._goto(INSTAGRAM_HOME_URL)
        self._debug_snapshot("01-home-opened")
        self._accept_cookies()
        self._debug_snapshot("02-home-after-cookies")
        time.sleep(2)

        if self._looks_logged_in():
            self._dismiss_interruptions()
            self._debug_snapshot("03-already-logged-in")
            return

        print("[Instagram] Opening login page...", flush=True)
        self._goto(INSTAGRAM_LOGIN_URL)
        self._debug_snapshot("04-login-opened")
        self._accept_cookies()
        self._debug_snapshot("05-login-after-cookies")
        time.sleep(2)

        if self.username:
            try:
                username_input = self.wait_for_any_selector(
                    [
                        "input[name='email']",
                        "input[name='username']",
                        "input[aria-label='Phone number, username, or email']",
                        "input[placeholder='Mobile number, username or email']",
                        "input[placeholder='Phone number, username, or email']",
                    ],
                    timeout_ms=15000,
                )
                username_input.click()
                username_input.fill(self.username)
                self._debug_snapshot("06-username-filled")
            except Exception:
                self._debug_snapshot("06-username-fill-failed")

        if self.password:
            try:
                password_input = self.wait_for_any_selector(
                    [
                        "input[name='pass']",
                        "input[name='password']",
                        "input[aria-label='Password']",
                        "input[type='password']",
                    ],
                    timeout_ms=10000,
                )
                password_input.click()
                password_input.fill(self.password)
                self._debug_snapshot("07-password-filled")
                time.sleep(0.5)
                print("[Instagram] Submitting login...", flush=True)
                self.wait_for_any_selector(
                    [
                        "button[aria-label='Log In']",
                        "[role='button'][aria-label='Log In']",
                        "button[type='submit']",
                        "button:has-text('Log in')",
                        "button:has-text('Log In')",
                        "[role='button']:has-text('Log in')",
                    ],
                    timeout_ms=10000,
                ).click()
                self._debug_snapshot("08-login-clicked")
            except Exception:
                self._debug_snapshot("08-login-click-failed")

        print(
            "[Instagram] Complete any login/captcha/2FA in the browser — will continue automatically once logged in..."
        )
        page.wait_for_function(
            '() => !window.location.href.includes(\'/accounts/login\') || document.querySelector(\'[aria-label="Create"], [aria-label="New post"], a[href="/create/style/"], a[href="/direct/inbox/"]\')',
            timeout=600000,
        )
        time.sleep(3)
        self._dismiss_interruptions()
        self._debug_snapshot("09-login-complete")

    def _goto(self, url):
        try:
            self.page.goto(url, wait_until="commit", timeout=15000)
        except Exception:
            # Instagram can keep long-lived requests open; keep using the loaded page.
            pass

    def _debug_snapshot(self, label):
        try:
            INSTAGRAM_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            safe_label = str(label).replace("/", "-")
            screenshot_path = INSTAGRAM_DEBUG_DIR / f"{safe_label}.png"
            json_path = INSTAGRAM_DEBUG_DIR / f"{safe_label}.json"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            summary = self.page.evaluate(
                """() => {
                    const visibleText = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style && style.visibility !== 'hidden' &&
                            style.display !== 'none' &&
                            rect.width > 0 &&
                            rect.height > 0;
                    };
                    const trim = (value) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, 160);
                    return {
                        url: window.location.href,
                        title: document.title,
                        bodyTextSnippet: trim(document.body ? document.body.innerText : ''),
                        inputs: Array.from(document.querySelectorAll('input')).slice(0, 20).map((input) => ({
                            type: input.type,
                            name: input.name,
                            placeholder: input.placeholder,
                            ariaLabel: input.getAttribute('aria-label'),
                            visible: visibleText(input),
                            hasValue: Boolean(input.value),
                        })),
                        buttons: Array.from(document.querySelectorAll('button, [role="button"]'))
                            .filter(visibleText)
                            .slice(0, 30)
                            .map((button) => ({
                                text: trim(button.innerText || button.textContent),
                                ariaLabel: button.getAttribute('aria-label'),
                                type: button.getAttribute('type'),
                            })),
                        links: Array.from(document.querySelectorAll('a'))
                            .filter(visibleText)
                            .slice(0, 20)
                            .map((link) => ({
                                text: trim(link.innerText || link.textContent),
                                href: link.href,
                            })),
                    };
                }"""
            )
            json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(
                f"[Instagram][debug] {label}: {summary.get('url')} -> {screenshot_path}", flush=True
            )
        except Exception as exc:
            print(f"[Instagram][debug] {label}: snapshot failed: {exc}", flush=True)

    def _accept_cookies(self):
        for selector in [
            "button:has-text('Allow all cookies')",
            "button:has-text('Accept all cookies')",
            "button:has-text('Accept Cookies')",
            "button:has-text('Accept cookies')",
            "button:has-text('Accept All')",
            "button:has-text('Accept all')",
            "button:has-text('Allow All')",
            "button:has-text('Allow all')",
            "div[role='button']:has-text('Allow all cookies')",
            "div[role='button']:has-text('Accept all cookies')",
        ]:
            try:
                button = self.page.locator(selector).first
                if button.is_visible(timeout=2000):
                    button.click()
                    time.sleep(1)
                    return True
            except Exception:
                pass
        return False

    def _looks_logged_in(self):
        for selector in [
            "svg[aria-label='Home']",
            "[aria-label='Home']",
            "svg[aria-label='Create']",
            "[aria-label='Create']",
            "svg[aria-label='New post']",
            "[aria-label='New post']",
            "a[href='/direct/inbox/']",
        ]:
            try:
                if self.page.locator(selector).first.is_visible(timeout=1000):
                    return True
            except Exception:
                pass
        return False

    def _dismiss_interruptions(self):
        for selector in [
            "button:has-text('Not now')",
            "button:has-text('Not Now')",
            "div[role='button']:has-text('Not now')",
            "div[role='button']:has-text('Not Now')",
        ]:
            try:
                button = self.page.locator(selector).first
                if button.is_visible(timeout=2000):
                    button.click()
                    time.sleep(0.5)
            except Exception:
                pass

    def _click_create(self):
        create_button = self.wait_for_any_selector(
            [
                "[aria-label='Create']",
                "[aria-label='New post']",
                "svg[aria-label='Create']",
                "svg[aria-label='New post']",
                "a[href='/create/style/']",
                "a[href='/create/select/']",
            ],
            timeout_ms=30000,
        )
        create_button.click()

    def _click_post_from_create_menu(self):
        self._debug_snapshot("11-create-menu-open")
        create_box = None
        try:
            create_box = self.page.locator(
                "a:has-text('Create'), [aria-label='Create']"
            ).first.bounding_box()
        except Exception:
            pass
        if create_box:
            self.page.mouse.click(create_box["x"] + 85, create_box["y"] + 50)
            time.sleep(2)
            self._debug_snapshot("11b-post-menu-clicked-by-coordinate")
            if self._has_upload_prompt():
                return

        selectors = [
            "a:has-text('Post')",
            "div[role='button']:has-text('Post')",
            "span:has-text('Post')",
            "[aria-label='Post']",
        ]
        for selector in selectors:
            try:
                items = self.page.locator(selector)
                count = min(items.count(), 10)
                for index in range(count):
                    item = items.nth(index)
                    if item.is_visible(timeout=1000):
                        item.click()
                        time.sleep(2)
                        self._debug_snapshot("11b-post-menu-clicked")
                        if self._has_upload_prompt():
                            return
            except Exception:
                pass

        clicked = self.page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none';
                };
                const candidates = Array.from(document.querySelectorAll('a, button, [role="button"], span, div'))
                    .filter(isVisible)
                    .filter((el) => (el.innerText || el.textContent || '').trim() === 'Post');
                const target = candidates[0];
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
        time.sleep(2)
        self._debug_snapshot("11b-post-menu-clicked-js")
        if not clicked:
            raise RuntimeError(
                "Instagram Create menu opened, but no visible Post option was found."
            )

    def _has_upload_prompt(self):
        try:
            if self.page.locator("input[type='file']").first.count() > 0:
                return True
        except Exception:
            pass
        for selector in [
            "button:has-text('Select from computer')",
            "div[role='button']:has-text('Select from computer')",
            "button:has-text('Select From Computer')",
            "div[role='button']:has-text('Select From Computer')",
        ]:
            try:
                if self.page.locator(selector).first.is_visible(timeout=1000):
                    return True
            except Exception:
                pass
        return False

    def _set_video_file(self, video_path):
        resolved_video = str(Path(video_path).expanduser().resolve())
        self._debug_snapshot("12-before-file-select")
        chooser_selectors = [
            "button:has-text('Select from computer')",
            "button:has-text('Select From Computer')",
            "button:has-text('Select from device')",
            "button:has-text('Select from your device')",
            "button:has-text('Upload')",
            "div[role='button']:has-text('Select from computer')",
            "div[role='button']:has-text('Select From Computer')",
            "div[role='button']:has-text('Select from device')",
            "div[role='button']:has-text('Select from your device')",
            "div[role='button']:has-text('Upload')",
        ]
        try:
            with self.page.expect_file_chooser(timeout=15000) as file_chooser_info:
                select_button = self.wait_for_any_selector(chooser_selectors, timeout_ms=30000)
                select_button.click()
            file_chooser_info.value.set_files(resolved_video)
            time.sleep(8)
            self._debug_snapshot("13-file-set-via-chooser")
            return
        except Exception:
            self._debug_snapshot("13-file-chooser-failed")

        self.page.wait_for_selector("input[type='file']", timeout=15000, state="attached")
        self.page.locator("input[type='file']").first.set_input_files(resolved_video)
        time.sleep(8)
        self._debug_snapshot("13-file-set-via-input")

    def _click_if_visible(self, selectors, timeout_ms=3000):
        for selector in selectors:
            try:
                item = self.page.locator(selector).first
                if item.is_visible(timeout=timeout_ms):
                    item.click()
                    time.sleep(1)
                    return True
            except Exception:
                pass
        return False

    def _advance_to_caption(self):
        caption_selector = (
            "div[aria-label='Write a caption...'], "
            "textarea[aria-label='Write a caption...'], "
            "div[contenteditable='true']"
        )
        for _ in range(5):
            try:
                if self.page.locator(caption_selector).first.is_visible(timeout=1000):
                    self._debug_snapshot("14-caption-visible")
                    return
            except Exception:
                pass
            clicked = self._click_if_visible(
                [
                    "[aria-label='Next']",
                    "button[aria-label='Next']",
                    "div[role='button'][aria-label='Next']",
                    "button:has-text('OK')",
                    "div[role='button']:has-text('OK')",
                    "button:has-text('Next')",
                    "div[role='button']:has-text('Next')",
                ],
                timeout_ms=4000,
            )
            self._debug_snapshot("14-after-advance-click")
            time.sleep(2)
            if not clicked:
                break

    def _fill_caption(self, caption):
        try:
            caption_area = self.wait_for_any_selector(
                [
                    "div[aria-label='Write a caption...']",
                    "textarea[aria-label='Write a caption...']",
                    "div[contenteditable='true']",
                ],
                timeout_ms=5000,
            )
            caption_area.click()
            try:
                caption_area.fill(caption)
            except Exception:
                self.page.keyboard.press("Meta+A")
                self.page.keyboard.insert_text(caption)
        except Exception:
            # Current Instagram web reel composer has a blank caption region without a stable label.
            self.page.mouse.click(1110, 255)
            time.sleep(0.5)
            self.page.keyboard.insert_text(caption)
        time.sleep(1)
        self._debug_snapshot("15-caption-filled")

    def _click_text_candidate(self, texts, timeout_ms=3000):
        selectors = []
        for text in texts:
            selectors.extend(
                [
                    f"button:has-text('{text}')",
                    f"div[role='button']:has-text('{text}')",
                    f"[role='button']:has-text('{text}')",
                    f"span:has-text('{text}')",
                    f"div:has-text('{text}')",
                ]
            )
        return self._click_if_visible(selectors, timeout_ms=timeout_ms)

    def _set_cover_photo(self, cover_path):
        if not cover_path:
            return

        resolved_cover = Path(cover_path).expanduser().resolve()
        if not resolved_cover.exists():
            raise FileNotFoundError(f"Instagram cover image was not found: {resolved_cover}")

        self._debug_snapshot("15a-before-cover")
        opened = self._click_text_candidate(
            ["Edit cover", "Cover photo", "Cover"],
            timeout_ms=3000,
        )
        if not opened:
            print(
                "[Instagram] Cover editor control was not found; continuing with the generated cover intro.",
                flush=True,
            )
            self._debug_snapshot("15b-cover-editor-missing")
            return

        time.sleep(1)
        self._debug_snapshot("15b-cover-editor-open")

        upload_selectors = [
            "button:has-text('Add from computer')",
            "div[role='button']:has-text('Add from computer')",
            "button:has-text('From computer')",
            "div[role='button']:has-text('From computer')",
            "button:has-text('Select from computer')",
            "div[role='button']:has-text('Select from computer')",
            "button:has-text('Upload from computer')",
            "div[role='button']:has-text('Upload from computer')",
        ]
        try:
            with self.page.expect_file_chooser(timeout=10000) as file_chooser_info:
                self.wait_for_any_selector(upload_selectors, timeout_ms=15000).click()
            file_chooser_info.value.set_files(str(resolved_cover))
        except Exception:
            try:
                file_input = self.page.locator("input[type='file']").first
                file_input.set_input_files(str(resolved_cover))
            except Exception as exc:
                self._debug_snapshot("15c-cover-upload-failed")
                raise RuntimeError(
                    "Instagram cover editor opened, but no cover upload control was found."
                ) from exc

        time.sleep(3)
        self._debug_snapshot("15c-cover-uploaded")
        if not self._click_text_candidate(["Done", "Apply"], timeout_ms=10000):
            self._debug_snapshot("15d-cover-done-missing")
            raise RuntimeError(
                "Instagram cover image was uploaded, but no Done/Apply button was found."
            )
        time.sleep(1)
        self._debug_snapshot("15e-cover-done")

    def _click_share(self):
        self._debug_snapshot("16-before-share")
        return self._click_submit_button(["Share"])

    def _click_submit_button(self, labels):
        # The final Instagram action often has visible text but flaky DOM hit
        # targets. The top-right modal coordinate has been more reliable.
        try:
            self.page.mouse.click(1245, 110)
            time.sleep(2)
            self._debug_snapshot("17-submit-clicked-coordinate")
            return
        except Exception:
            pass

        selectors = []
        for label in labels:
            selectors.extend(
                [
                    f"button:has-text('{label}')",
                    f"div[role='button']:has-text('{label}')",
                    f"[role='button']:has-text('{label}')",
                ]
            )
        try:
            button = self.wait_for_any_selector(selectors, timeout_ms=8000)
            button.click(force=True)
            time.sleep(2)
            self._debug_snapshot("17-submit-clicked-selector")
            return
        except Exception:
            pass

        raise RuntimeError(f"No visible submit button was found for labels: {labels}")

    def _parse_schedule_at(self, schedule_at):
        if isinstance(schedule_at, datetime):
            return schedule_at
        value = str(schedule_at or "").strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError(
                "Schedule time must look like '2026-05-22 18:30' or ISO format."
            ) from exc

    def _fill_first_visible_input(self, selectors, value):
        for selector in selectors:
            try:
                fields = self.page.locator(selector)
                count = min(fields.count(), 8)
                for index in range(count):
                    field = fields.nth(index)
                    if field.is_visible(timeout=1000):
                        field.click()
                        try:
                            field.fill(value)
                        except Exception:
                            self.page.keyboard.press("Meta+A")
                            self.page.keyboard.insert_text(value)
                        return True
            except Exception:
                pass
        return False

    def _set_schedule_time(self, schedule_at):
        scheduled_for = self._parse_schedule_at(schedule_at)
        if scheduled_for is None:
            return None

        self._debug_snapshot("16a-before-schedule")
        opened = self._click_text_candidate(
            ["Advanced settings", "Advanced Settings", "More options", "More Options"],
            timeout_ms=5000,
        )
        if not opened:
            self._debug_snapshot("16b-schedule-settings-missing")
            raise RuntimeError(
                "Instagram scheduling was requested, but Advanced settings was not visible. "
                f"See {INSTAGRAM_DEBUG_DIR / '16b-schedule-settings-missing.png'}."
            )

        time.sleep(1)
        self._debug_snapshot("16b-schedule-settings-open")
        enabled = self._click_text_candidate(
            [
                "Schedule this reel",
                "Schedule this post",
                "Schedule",
                "Set date and time",
            ],
            timeout_ms=5000,
        )
        if not enabled:
            self._debug_snapshot("16c-schedule-control-missing")
            raise RuntimeError(
                "Instagram scheduling was requested, but no Schedule control was visible. "
                "This may require a professional Instagram account or Meta's current composer UI. "
                f"See {INSTAGRAM_DEBUG_DIR / '16c-schedule-control-missing.png'}."
            )

        time.sleep(1)
        self._debug_snapshot("16c-schedule-control-open")
        date_value = scheduled_for.strftime("%m/%d/%Y")
        iso_date_value = scheduled_for.strftime("%Y-%m-%d")
        time_value = scheduled_for.strftime("%H:%M")

        date_filled = self._fill_first_visible_input(
            [
                "input[type='date']",
                "input[placeholder*='mm/dd']",
                "input[placeholder*='MM/DD']",
                "input[aria-label*='Date']",
                "input[aria-label*='date']",
            ],
            iso_date_value,
        ) or self._fill_first_visible_input(["input"], date_value)
        time_filled = self._fill_first_visible_input(
            [
                "input[type='time']",
                "input[placeholder*='time']",
                "input[placeholder*='Time']",
                "input[aria-label*='Time']",
                "input[aria-label*='time']",
            ],
            time_value,
        )

        if not (date_filled and time_filled):
            self._debug_snapshot("16d-schedule-fields-missing")
            raise RuntimeError(
                "Instagram scheduling was requested, but date/time fields could not be filled. "
                f"See {INSTAGRAM_DEBUG_DIR / '16d-schedule-fields-missing.png'}."
            )

        self._debug_snapshot("16d-schedule-fields-filled")
        self._click_text_candidate(["Done", "Set time", "Schedule"], timeout_ms=5000)
        time.sleep(1)
        self._debug_snapshot("16e-schedule-set")
        return scheduled_for

    def _body_text_contains(self, snippets):
        try:
            body_text = self.page.locator("body").inner_text(timeout=3000).lower()
        except Exception:
            return False
        return any(snippet.lower() in body_text for snippet in snippets)

    def _wait_for_share_result(self, timeout_seconds=300, scheduled=False):
        success_snippets = [
            "your reel has been shared",
            "your post has been shared",
            "reel shared",
            "post shared",
        ]
        if scheduled:
            success_snippets.extend(
                [
                    "your reel has been scheduled",
                    "your post has been scheduled",
                    "successfully scheduled",
                    "reel scheduled",
                    "post scheduled",
                ]
            )
        error_snippets = [
            "couldn't share",
            "could not share",
            "couldn't upload",
            "could not upload",
            "something went wrong",
            "try again",
            "failed",
            "error",
        ]
        deadline = time.time() + timeout_seconds
        snapshot_index = 0

        while time.time() < deadline:
            if self._body_text_contains(success_snippets):
                self._debug_snapshot("18-share-success")
                return
            if self._body_text_contains(error_snippets):
                self._debug_snapshot("18-share-error")
                raise RuntimeError(
                    "Instagram reported an error while sharing. "
                    f"See {INSTAGRAM_DEBUG_DIR / '18-share-error.png'}."
                )
            if snapshot_index % 6 == 0:
                self._debug_snapshot(f"18-sharing-wait-{snapshot_index:02d}")
            snapshot_index += 1
            time.sleep(5)

        self._debug_snapshot("18-share-timeout")
        raise RuntimeError(
            "Instagram did not confirm the reel was shared before the timeout. "
            f"See {INSTAGRAM_DEBUG_DIR / '18-share-timeout.png'}."
        )

    def upload_video(self, video_path, *, caption, cover_path=None, schedule_at=None):
        self.ensure_logged_in()
        caption = caption or ""
        self._debug_snapshot("10-before-create-open")
        self._click_create()
        time.sleep(2)
        self._debug_snapshot("11-after-create-open")
        self._click_post_from_create_menu()

        self._set_video_file(video_path)
        self._advance_to_caption()
        self._set_cover_photo(cover_path)
        self._fill_caption(caption)
        scheduled_for = self._set_schedule_time(schedule_at)

        if scheduled_for:
            self._debug_snapshot("16-before-schedule-submit")
            self._click_submit_button(["Schedule", "Share"])
            self._wait_for_share_result(scheduled=True)
            status = "scheduled"
        else:
            self._click_share()
            self._wait_for_share_result()
            status = "shared"

        return {
            "status": status,
            "platform": "instagram",
            "video_path": str(Path(video_path).expanduser().resolve()),
            "cover_path": str(Path(cover_path).expanduser().resolve()) if cover_path else None,
            "caption": caption,
            "scheduled_for": scheduled_for.isoformat(timespec="minutes") if scheduled_for else None,
        }
