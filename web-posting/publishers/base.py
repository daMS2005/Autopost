import time
from pathlib import Path


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
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            channel="chrome",
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
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
            f"() => window.location.href.includes({fragment!r})",
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
