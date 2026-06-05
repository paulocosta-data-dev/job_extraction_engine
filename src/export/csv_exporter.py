import csv
from datetime import datetime
from pathlib import Path

import duckdb


EXPORT_DIR = Path("data/exports")

COLUMNS = [
    "linkedin_job_id",
    "title",
    "company",
    "location",
    "workplace_type",
    "employment_type",
    "salary",
    "job_url",
    "source_search_url",
    "first_seen",
    "last_seen",
    "description",
]


def export_to_csv(connection: duckdb.DuckDBPyConnection) -> Path:
    """
    Export jobs_current to a timestamped CSV in data/exports/.
    Returns the path of the created file.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"jobs_{timestamp}.csv"

    rows = connection.execute(
        f"SELECT {', '.join(COLUMNS)} FROM jobs_current ORDER BY first_seen DESC"
    ).fetchall()

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    return path
