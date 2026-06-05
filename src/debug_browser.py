"""
Browser control debug script.

Purpose: Systematically validate whether Playwright has live control
         of the Chrome instance before any extraction logic runs.

Run from: job_extraction_engine/
Command:  python src/debug_browser.py

Checks performed:
  1. Chrome process state before launch
  2. Launch with diagnostic args
  3. Event listener registration (new page, console, request)
  4. Programmatic goto + URL verification
  5. DOM accessibility check
  6. Fallback: Chromium (no channel) to isolate chrome-specific issues
"""

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

PROFILE_PATH = Path("profiles/linkedin")
TARGET_URL = "https://example.com"  # Neutral target, avoids auth complexity


# ---------------------------------------------------------------------------
# Step 0 — Chrome process check
# ---------------------------------------------------------------------------

def check_chrome_processes() -> int:
    print("\n[STEP 0] Checking for running Chrome processes...")
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        lines = [l for l in result.stdout.strip().splitlines() if "chrome.exe" in l]
        count = len(lines)
        if count:
            print(f"  WARNING: {count} Chrome process(es) already running.")
            print("  These may conflict with Playwright's persistent context.")
            print("  Recommendation: kill them before running this script.")
            print("    taskkill /IM chrome.exe /F")
        else:
            print("  OK: No Chrome processes found.")
        return count
    except Exception as e:
        print(f"  SKIP: Could not query processes ({e})")
        return -1


# ---------------------------------------------------------------------------
# Step 1 — Launch with diagnostic args
# ---------------------------------------------------------------------------

def build_launch_args() -> list[str]:
    return [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=ChromeWhatsNewUI",
    ]


def clean_profile_locks() -> None:
    """Remove stale Chrome singleton lock files that cause launch hangs."""
    lock_files = [
        PROFILE_PATH / "SingletonLock",
        PROFILE_PATH / "SingletonCookie",
        PROFILE_PATH / "SingletonSocket",
    ]
    removed = []
    for lock in lock_files:
        if lock.exists():
            lock.unlink()
            removed.append(lock.name)
    if removed:
        print(f"  Removed stale lock files: {', '.join(removed)}")
    else:
        print("  No stale lock files found.")


def launch_context(playwright, use_system_chrome: bool) -> BrowserContext:
    PROFILE_PATH.mkdir(parents=True, exist_ok=True)
    clean_profile_locks()

    launch_kwargs = dict(
        user_data_dir=str(PROFILE_PATH),
        headless=False,
        args=build_launch_args(),
        slow_mo=100,  # Makes page transitions visible
    )

    if use_system_chrome:
        print("  Mode: system Chrome (channel='chrome')")
        launch_kwargs["channel"] = "chrome"
    else:
        print("  Mode: bundled Chromium (no channel)")

    return playwright.chromium.launch_persistent_context(**launch_kwargs)


# ---------------------------------------------------------------------------
# Step 2 — Instrument context with event listeners
# ---------------------------------------------------------------------------

def attach_listeners(context: BrowserContext) -> None:
    def on_new_page(page: Page) -> None:
        print(f"  [EVENT] new page opened: {page.url!r}")

        # Also listen for navigations on new pages
        page.on("framenavigated", lambda frame: print(
            f"  [EVENT] framenavigated on new page -> {frame.url!r}"
        ))

    context.on("page", on_new_page)
    print("  OK: Event listeners attached (new page, framenavigated)")


# ---------------------------------------------------------------------------
# Step 3 — Validate goto on the initial page
# ---------------------------------------------------------------------------

def validate_goto(page: Page, label: str) -> bool:
    print(f"\n[STEP 3] Programmatic goto ({label})...")
    print(f"  URL before goto: {page.url!r}")

    try:
        response = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=15000)

        url_after = page.url
        print(f"  URL after goto: {url_after!r}")

        if response:
            print(f"  HTTP status: {response.status}")
        else:
            print("  HTTP status: None (goto returned no response)")

        if url_after == "about:blank":
            print("  FAIL: URL is still about:blank after goto — ghost context confirmed.")
            return False

        if TARGET_URL in url_after or "example.com" in url_after:
            print("  OK: goto succeeded — Playwright controls the browser.")
            return True

        print(f"  UNEXPECTED: URL is {url_after!r} (not target, not blank).")
        return False

    except Exception as e:
        print(f"  ERROR during goto: {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 4 — DOM accessibility check
# ---------------------------------------------------------------------------

def validate_dom(page: Page) -> bool:
    print("\n[STEP 4] DOM accessibility check...")
    try:
        title = page.title()
        print(f"  page.title(): {title!r}")

        h1 = page.locator("h1").first.text_content(timeout=5000)
        print(f"  First <h1>: {h1!r}")

        print("  OK: DOM is readable.")
        return True

    except Exception as e:
        print(f"  FAIL: Cannot read DOM — {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 5 — Page count snapshot
# ---------------------------------------------------------------------------

def snapshot_pages(context: BrowserContext) -> None:
    pages = context.pages
    print(f"\n[SNAPSHOT] Pages in context: {len(pages)}")
    for i, p in enumerate(pages):
        print(f"  Page {i}: {p.url!r}")


# ---------------------------------------------------------------------------
# Main debug flow
# ---------------------------------------------------------------------------

def run_debug(use_system_chrome: bool) -> None:
    mode = "system Chrome" if use_system_chrome else "bundled Chromium"
    print(f"\n{'='*60}")
    print(f"  DEBUG RUN: {mode}")
    print(f"{'='*60}")

    with sync_playwright() as p:
        print("\n[STEP 1] Launching browser...")
        context = launch_context(p, use_system_chrome=use_system_chrome)
        print("  Browser launched.")

        print("\n[STEP 2] Attaching event listeners...")
        attach_listeners(context)

        # Brief pause — give Chrome time to settle before reading pages
        time.sleep(1)

        snapshot_pages(context)

        page = context.pages[0] if context.pages else context.new_page()
        print(f"\n  Active page selected: {page.url!r}")

        # Attach framenavigated listener to the initial page
        page.on("framenavigated", lambda frame: print(
            f"  [EVENT] framenavigated (initial page) -> {frame.url!r}"
        ))

        goto_ok = validate_goto(page, label=mode)

        if goto_ok:
            validate_dom(page)
        else:
            print("\n  Skipping DOM check (goto failed).")

        snapshot_pages(context)

        print("\n[STEP 5] Waiting 3 seconds — observe Chrome window state...")
        time.sleep(3)

        context.close()
        print("\n  Browser closed.")


def main() -> None:
    chrome_count = check_chrome_processes()

    if chrome_count > 0:
        answer = input(
            "\nChrome is running. Kill it now and press ENTER to continue, "
            "or type 'skip' to run anyway: "
        )
        if answer.strip().lower() != "skip":
            subprocess.run(["taskkill", "/IM", "chrome.exe", "/F"], capture_output=True)
            print("  Chrome processes terminated.")
            time.sleep(2)

    # Run 1: system Chrome (the failing scenario)
    run_debug(use_system_chrome=True)

    answer = input(
        "\n\nRun 2 will test with bundled Chromium (no channel='chrome').\n"
        "This isolates whether the issue is Chrome-specific.\n"
        "Press ENTER to continue, or type 'skip' to exit: "
    )
    if answer.strip().lower() == "skip":
        sys.exit(0)

    # Run 2: bundled Chromium (control group)
    run_debug(use_system_chrome=False)

    print("\n\nDEBUG COMPLETE.")
    print("Compare Run 1 vs Run 2 output.")
    print("If Run 1 fails and Run 2 succeeds: issue is Chrome-specific (process conflict).")
    print("If both fail: issue is in the persistent context setup or profile.")
    print("If both succeed: original issue was a running Chrome instance.")


if __name__ == "__main__":
    main()
