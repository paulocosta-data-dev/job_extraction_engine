from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright


class BrowserManager:
    PROFILE_PATH = Path("profiles/linkedin")

    def __init__(self) -> None:
        self.playwright = None
        self.context: BrowserContext | None = None

    def launch(self) -> BrowserContext:
        self.PROFILE_PATH.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.PROFILE_PATH),
            channel="chrome",
            headless=False,
        )

        return self.context

    def get_active_page(self) -> Page:
        if not self.context:
            raise RuntimeError(
                "Browser context has not been initialized."
            )

        if self.context.pages:
            return self.context.pages[0]

        return self.context.new_page()

    def get_all_pages(self) -> list[Page]:
        if not self.context:
            raise RuntimeError(
                "Browser context has not been initialized."
            )

        return self.context.pages

    def close(self) -> None:
        if self.context:
            self.context.close()

        if self.playwright:
            self.playwright.stop()