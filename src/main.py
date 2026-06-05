from pathlib import Path

from extraction.browser import BrowserManager, ChromeConflictError
from extraction.search_scraper import SearchScraper
from export.csv_exporter import export_to_csv
from storage.duckdb_client import DuckDBClient
from storage.repository import JobRepository

DATABASE_PATH = "data/duckdb/jobs.duckdb"


def get_db_client() -> DuckDBClient:
    Path("data/duckdb").mkdir(parents=True, exist_ok=True)
    client = DuckDBClient(DATABASE_PATH)
    client.connect()
    client.initialize_schema()
    return client


def run_extraction() -> None:
    browser_manager = BrowserManager()

    try:
        browser_manager.launch()
        page = browser_manager.get_active_page()

        print("\nNavigating to LinkedIn Jobs...")
        page.goto(
            "https://www.linkedin.com/jobs/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        print(f"Loaded: {page.url}")

        print("\n" + "=" * 60)
        print("Set up your LinkedIn job search:")
        print("  1. Enter keywords and location")
        print("  2. Apply filters (date, easy apply, etc.)")
        print("  3. Wait until the LEFT PANEL shows the list of job cards")
        print("  4. Only then press ENTER below")
        print("=" * 60)
        input("\nPress ENTER only after job cards are visible...\n")

        # --- Extraction ---
        scraper = SearchScraper(page)
        jobs = scraper.scrape()

        if not jobs:
            print("\nNo jobs extracted. Check that you are on a search results page.")
            input("\nPress ENTER to close the browser...")
            return

        print(f"\nExtracted {len(jobs)} job(s). Saving to database...")

        # --- Storage ---
        db = get_db_client()
        try:
            repo = JobRepository(db.connection)
            inserted, updated = repo.upsert_many(jobs)
            total = repo.count()
            print(f"  New jobs:     {inserted}")
            print(f"  Updated jobs: {updated}")
            print(f"  Total in DB:  {total}")

            csv_path = export_to_csv(db.connection)
            print(f"  CSV exported: {csv_path}")
        finally:
            db.close()

        input("\nPress ENTER to close the browser...")

    except ChromeConflictError as e:
        print(f"\nERROR: {e}")

    finally:
        browser_manager.close()


def main() -> None:
    run_extraction()


if __name__ == "__main__":
    main()
