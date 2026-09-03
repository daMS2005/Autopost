import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .base import BrowserPublisher

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

PROFILE_DIR = Path(__file__).resolve().parents[1] / "data" / "browser_profiles" / "instagram"
HOME_URL = "https://www.instagram.com/"
LOGIN_URL = "https://www.instagram.com/accounts/login/"


class InstagramPublisher(BrowserPublisher):
    def __init__(self, *, headless=False, slow_mo_ms=0):
        super().__init__(PROFILE_DIR, headless=headless, slow_mo_ms=slow_mo_ms)
        self.username = os.getenv("INSTAGRAM_USERNAME")
        self.password = os.getenv("INSTAGRAM_PASSWORD")

    def open_login_page(self):
        """Navigate to the Instagram login page and return immediately — for manual login flows."""
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        if self.username:
            try:
                field = self.wait_for_any_selector(
                    ["input[name='username']", "input[aria-label='Phone number, username, or email']"],
                    timeout_ms=15000,
                )
                field.click()
                field.press_sequentially(self.username, delay=80)
            except Exception:
                pass
        if self.password:
            try:
                field = self.wait_for_any_selector(
                    ["input[name='password']", "input[aria-label='Password']"],
                    timeout_ms=10000,
                )
                field.click()
                field.press_sequentially(self.password, delay=80)
            except Exception:
                pass

    def ensure_logged_in(self):
        page = self.page
        print("[Instagram] Opening Instagram...", flush=True)
        self._goto(HOME_URL)
        self._accept_cookies()
        time.sleep(2)

        if self._looks_logged_in():
            self._dismiss_interruptions()
            return

        print("[Instagram] Opening login page...", flush=True)
        self._goto(LOGIN_URL)
        self._accept_cookies()
        time.sleep(2)

        if self.username:
            try:
                field = self.wait_for_any_selector(
                    [
                        "input[name='username']",
                        "input[aria-label='Phone number, username, or email']",
                        "input[placeholder='Mobile number, username or email']",
                        "input[placeholder='Phone number, username, or email']",
                    ],
                    timeout_ms=15000,
                )
                field.click()
                field.fill(self.username)
            except Exception:
                pass

        if self.password:
            try:
                field = self.wait_for_any_selector(
                    ["input[name='password']", "input[aria-label='Password']"],
                    timeout_ms=10000,
                )
                field.click()
                field.fill(self.password)
                time.sleep(0.5)
                print("[Instagram] Submitting login...", flush=True)
                self.wait_for_any_selector(
                    ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Log In')"],
                    timeout_ms=10000,
                ).click()
            except Exception:
                pass

        print("[Instagram] Logging in — if a captcha appears, solve it in the browser and it will continue automatically...")
        page.wait_for_function(
            "() => !window.location.href.includes('/accounts/login') || document.querySelector('[aria-label=\"Create\"], [aria-label=\"New post\"], a[href=\"/create/style/\"], a[href=\"/direct/inbox/\"]')",
            timeout=600000,
        )
        page.wait_for_load_state("networkidle")
        self._dismiss_interruptions()

    def _goto(self, url):
        try:
            self.page.goto(url, wait_until="commit", timeout=15000)
        except Exception:
            # Instagram can keep long-lived requests open; keep using the loaded page.
            pass

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
        page = self.page
        selectors = [
            "svg[aria-label='Home']",
            "[aria-label='Home']",
            "svg[aria-label='Create']",
            "[aria-label='Create']",
            "svg[aria-label='New post']",
            "[aria-label='New post']",
            "a[href='/direct/inbox/']",
        ]
        for selector in selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=1000):
                    return True
            except Exception:
                pass
        return False

    def _dismiss_interruptions(self):
        """Dismiss non-essential Instagram prompts after login."""
        page = self.page
        for selector in [
            "button:has-text('Not now')",
            "button:has-text('Not Now')",
            "div[role='button']:has-text('Not now')",
            "div[role='button']:has-text('Not Now')",
        ]:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=2000):
                    button.click()
                    time.sleep(0.5)
            except Exception:
                pass

    def _click_create(self):
        create_btn = self.wait_for_any_selector(
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
        create_btn.click()

    def _set_video_file(self, video_path):
        page = self.page
        resolved_video = str(Path(video_path).expanduser().resolve())
        try:
            page.wait_for_selector("input[type='file']", timeout=10000, state="attached")
            page.locator("input[type='file']").first.set_input_files(resolved_video)
            return
        except Exception:
            pass

        with page.expect_file_chooser() as fc_info:
            select_btn = self.wait_for_any_selector(
                [
                    "button:has-text('Select from computer')",
                    "button:has-text('Select From Computer')",
                    "div[role='button']:has-text('Select from computer')",
                    "div[role='button']:has-text('Select From Computer')",
                ],
                timeout_ms=30000,
            )
            select_btn.click()
        fc_info.value.set_files(resolved_video)

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
        page = self.page
        caption_selector = (
            "div[aria-label='Write a caption...'], "
            "textarea[aria-label='Write a caption...'], "
            "div[contenteditable='true']"
        )
        for _ in range(5):
            try:
                if page.locator(caption_selector).first.is_visible(timeout=1000):
                    return
            except Exception:
                pass
            clicked = self._click_if_visible(
                [
                    "button:has-text('OK')",
                    "div[role='button']:has-text('OK')",
                    "button:has-text('Next')",
                    "div[role='button']:has-text('Next')",
                ],
                timeout_ms=4000,
            )
            if not clicked:
                break

    def _fill_caption(self, caption):
        caption_area = self.wait_for_any_selector(
            [
                "div[aria-label='Write a caption...']",
                "textarea[aria-label='Write a caption...']",
                "div[contenteditable='true']",
            ],
            timeout_ms=30000,
        )
        caption_area.click()
        try:
            caption_area.fill(caption)
        except Exception:
            self.page.keyboard.press("Meta+A")
            self.page.keyboard.insert_text(caption)

    def post_reel(self, video_path, *, caption):
        """Upload a video as an Instagram Reel."""
        page = self.page
        self.ensure_logged_in()
        caption = caption or ""

        self._click_create()

        # Choose "Post" from the dropdown if it appears
        try:
            post_option = page.locator("span:has-text('Post'), a:has-text('Post'), div[role='button']:has-text('Post')").first
            if post_option.is_visible(timeout=3000):
                post_option.click()
        except Exception:
            pass

        self._set_video_file(video_path)
        self._advance_to_caption()
        self._fill_caption(caption)

        # Share
        share_btn = self.wait_for_any_selector(
            ["button:has-text('Share')", "div[role='button']:has-text('Share')"],
            timeout_ms=30000,
        )
        share_btn.click()

        # Wait for the confirmation screen
        try:
            page.wait_for_selector(
                "span:has-text('Your reel has been shared'), span:has-text('Post shared'), span:has-text('Reel shared')",
                timeout=120000,
            )
        except Exception:
            pass  # Some accounts go straight back to feed

        return {
            "status": "submitted",
            "platform": "instagram",
            "video_path": str(Path(video_path).expanduser().resolve()),
            "caption": caption,
        }
