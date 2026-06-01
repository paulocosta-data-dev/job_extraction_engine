from pathlib import Path

from extraction.browser import BrowserManager
from storage.duckdb_client import DuckDBClient


def initialize_database() -> None:
    database_path = "data/duckdb/jobs.duckdb"

    Path("data/duckdb").mkdir(
        parents=True,
        exist_ok=True,
    )

    client = DuckDBClient(database_path)

    try:
        client.connect()
        client.initialize_schema()

        print("DuckDB initialized successfully.")

    finally:
        client.close()


def initialize_browser() -> None:
    browser_manager = BrowserManager()

    try:
        browser_manager.launch()

        page = browser_manager.get_active_page()

        print()
        print("Opening LinkedIn Jobs...")
        print()

        page.goto(
            "https://www.linkedin.com/jobs/",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        print()
        print("Current URL:")
        print(page.url)

        print()
        print("All pages:")

        for index, current_page in enumerate(
            browser_manager.get_all_pages(),
            start=1,
        ):
            print(
                f"Page {index}: {current_page.url}"
            )

        input("\nPress ENTER to close browser...")

    finally:
        browser_manager.close()


def main() -> None:
    initialize_database()
    initialize_browser()


if __name__ == "__main__":
    main()