"""
JobRepository — persists Job objects to DuckDB.

Two tables, two responsibilities:

  jobs_raw      Append-only scrape log.  Every job seen in every run is
                inserted here with its scrape_timestamp.  Never deduplicated.
                Use for auditing, debugging, and trend analysis.

  jobs_current  Deduplicated current state, keyed on linkedin_job_id.
                UPSERT semantics:
                  - New job     → INSERT with first_seen = scrape_timestamp
                  - Known job   → UPDATE last_seen + all fields EXCEPT first_seen
                scrape_timestamp is NOT stored here (it lives in jobs_raw).
"""

from datetime import datetime

import duckdb

from models.job import Job


class JobRepository:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def upsert(self, job: Job) -> None:
        """
        Persist one job.

        Always appends to jobs_raw (full audit trail).
        Upserts into jobs_current (dedup by linkedin_job_id):
          - first_seen is set only on first insert, never overwritten.
          - last_seen is always updated to the current scrape_timestamp.
        """
        self._insert_raw(job)
        self._upsert_current(job)

    def upsert_many(self, jobs: list[Job]) -> tuple[int, int]:
        """
        Persist a list of jobs.  Returns (inserted, updated) counts.
        """
        inserted = 0
        updated = 0
        for job in jobs:
            is_new = not self._exists(job.linkedin_job_id)
            self.upsert(job)
            if is_new:
                inserted += 1
            else:
                updated += 1
        return inserted, updated

    def count(self) -> int:
        """Return the total number of unique jobs in jobs_current."""
        row = self._conn.execute("SELECT COUNT(*) FROM jobs_current").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _exists(self, linkedin_job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jobs_current WHERE linkedin_job_id = ?",
            [linkedin_job_id],
        ).fetchone()
        return row is not None

    def _insert_raw(self, job: Job) -> None:
        self._conn.execute(
            """
            INSERT INTO jobs_raw (
                scrape_timestamp,
                source_platform,
                source_search_url,
                linkedin_job_id,
                title,
                company,
                location,
                workplace_type,
                employment_type,
                salary,
                posting_date,
                job_url,
                description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                job.scrape_timestamp,
                job.source_platform,
                job.source_search_url,
                job.linkedin_job_id,
                job.title,
                job.company,
                job.location,
                job.workplace_type,
                job.employment_type,
                job.salary,
                job.posting_date,
                job.job_url,
                job.description,
            ],
        )

    def _upsert_current(self, job: Job) -> None:
        """
        INSERT if new; UPDATE (all except first_seen) if already present.

        DuckDB ON CONFLICT syntax:
            ON CONFLICT (key) DO UPDATE SET col = EXCLUDED.col, ...
        EXCLUDED refers to the row that failed to insert.
        first_seen is intentionally absent from the DO UPDATE clause.
        """
        self._conn.execute(
            """
            INSERT INTO jobs_current (
                linkedin_job_id,
                source_platform,
                source_search_url,
                title,
                company,
                location,
                workplace_type,
                employment_type,
                salary,
                posting_date,
                job_url,
                description,
                first_seen,
                last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (linkedin_job_id) DO UPDATE SET
                source_search_url = EXCLUDED.source_search_url,
                title             = EXCLUDED.title,
                company           = EXCLUDED.company,
                location          = EXCLUDED.location,
                workplace_type    = EXCLUDED.workplace_type,
                employment_type   = EXCLUDED.employment_type,
                salary            = EXCLUDED.salary,
                posting_date      = EXCLUDED.posting_date,
                job_url           = EXCLUDED.job_url,
                description       = EXCLUDED.description,
                last_seen         = EXCLUDED.last_seen
                -- first_seen is NOT updated: it preserves the original discovery date
            """,
            [
                job.linkedin_job_id,
                job.source_platform,
                job.source_search_url,
                job.title,
                job.company,
                job.location,
                job.workplace_type,
                job.employment_type,
                job.salary,
                job.posting_date,
                job.job_url,
                job.description,
                job.scrape_timestamp,   # first_seen (only used on INSERT)
                job.scrape_timestamp,   # last_seen  (always updated)
            ],
        )
