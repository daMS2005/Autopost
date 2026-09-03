import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .base import BrowserPublisher

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

PROFILE_DIR = Path(__file__).resolve().parents[1] / "data" / "browser_profiles" / "tiktok"
UPLOAD_URL = "https://www.tiktok.com/upload?lang=en"
EMAIL_LOGIN_URL = "https://www.tiktok.com/login/phone-or-email/email"


class TikTokPublisher(BrowserPublisher):
    def __init__(self, *, headless=False, slow_mo_ms=0):
        super().__init__(PROFILE_DIR, headless=headless, slow_mo_ms=slow_mo_ms)
        self.identifier = (
            os.getenv("TIKTOK_LOGIN_EMAIL")
            or os.getenv("TIKTOK_LOGIN_USERNAME")
            or os.getenv("TIKTOK_LOGIN_PHONE")
        )
        self.password = os.getenv("TIKTOK_LOGIN_PASSWORD")

    def open_login_page(self):
        """Navigate to the TikTok login page and return immediately — for manual login flows."""
        self.page.goto(EMAIL_LOGIN_URL, wait_until="domcontentloaded")
        if self.identifier:
            try:
                self.wait_for_any_selector(
                    ["input[name='username']", "input[placeholder*='Email']", "input[type='text']"],
                    timeout_ms=15000,
                ).fill(self.identifier)
            except Exception:
                pass
        if self.password:
            try:
                self.wait_for_any_selector(
                    ["input[type='password']", "input[name='password']"],
                    timeout_ms=10000,
                ).fill(self.password)
            except Exception:
                pass

    def ensure_logged_in(self):
        page = self.page
        page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        try:
            already_logged_in = "/login" not in page.url and not page.locator("text=Log in").first.is_visible(timeout=2000)
        except Exception:
            already_logged_in = False

        if already_logged_in:
            return

        page.goto(EMAIL_LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        if self.identifier:
            try:
                self.wait_for_any_selector(
                    ["input[name='username']", "input[placeholder*='Email']", "input[type='text']"],
                    timeout_ms=15000,
                ).fill(self.identifier)
            except Exception:
                pass

        if self.password:
            try:
                self.wait_for_any_selector(
                    ["input[type='password']", "input[name='password']"],
                    timeout_ms=10000,
                ).fill(self.password)
            except Exception:
                pass

        print("[TikTok] Complete the login/captcha in the browser — will continue automatically once logged in...")
        page.wait_for_function(
            "() => !window.location.href.includes('/login')",
            timeout=600000,
        )
        page.wait_for_load_state("networkidle")

    def post_video(self, video_path, *, caption):
        page = self.page
        self.ensure_logged_in()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded")
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

        # Wait for the video to finish processing before posting
        time.sleep(3)

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
