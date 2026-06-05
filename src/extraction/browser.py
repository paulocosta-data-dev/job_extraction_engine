import subprocess
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright


class ChromeConflictError(RuntimeError):
    """Raised when Chrome processes are detected before launch."""


class BrowserManager:
    PROFILE_PATH = Path("profiles/linkedin")

    # Lock files Chrome leaves behind after a crash or force-kill.
    # If present at launch time they cause launch_persistent_context to hang.
    _LOCK_FILES = (
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
    )

    def __init__(self) -> None:
        self.playwright = None
        self.context: BrowserContext | None = None

    # ------------------------------------------------------------------
    # Pre-launch guards
    # ------------------------------------------------------------------

    def _check_chrome_processes(self) -> None:
        """
        Raise ChromeConflictError if system Chrome is already running.

        launch_persistent_context with channel='chrome' can silently attach
        to an existing Chrome process and return a ghost context whose pages
        never reflect real navigation. Fail fast here instead.
        """
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
            )
            running = [
                line for line in result.stdout.splitlines()
                if "chrome.exe" in line
            ]
            if running:
                raise ChromeConflictError(
                    f"{len(running)} Chrome process(es) are already running. "
                    "Close Chrome before launching the extraction engine.\n"
                    "  taskkill /IM chrome.exe /F"
                )
        except ChromeConflictError:
            raise
        except Exception:
            # tasklist unavailable (non-Windows or permission issue) — skip.
            pass

    def _clean_profile_locks(self) -> None:
        """
        Remove stale singleton lock files from the profile directory.

        Chrome leaves these behind after a crash or force-kill. A subsequent
        launch_persistent_context call will hang waiting for the lock to clear
        unless they are removed first.
        """
        for name in self._LOCK_FILES:
            lock = self.PROFILE_PATH / name
            if lock.exists():
                lock.unlink()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch(self) -> BrowserContext:
        self.PROFILE_PATH.mkdir(parents=True, exist_ok=True)

        self._check_chrome_processes()
        self._clean_profile_locks()

        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.PROFILE_PATH),
            channel="chrome",
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=ChromeWhatsNewUI",
            ],
        )

        return self.context

    def get_active_page(self) -> Page:
        if not self.context:
            raise RuntimeError("Browser context has not been initialized.")

        if self.context.pages:
            return self.context.pages[0]

        return self.context.new_page()

    def get_all_pages(self) -> list[Page]:
        if not self.context:
            raise RuntimeError("Browser context has not been initialized.")

        return self.context.pages

    def close(self) -> None:
        if self.context:
            self.context.close()

        if self.playwright:
            self.playwright.stop()
