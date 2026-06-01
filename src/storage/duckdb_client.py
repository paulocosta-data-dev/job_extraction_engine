import duckdb


class DuckDBClient:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.connection = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        try:
            self.connection = duckdb.connect(
                self.database_path
            )

            return self.connection

        except duckdb.IOException as exc:
            raise RuntimeError(
                f"Invalid DuckDB database file: {self.database_path}"
            ) from exc

    def close(self) -> None:
        if self.connection:
            self.connection.close()

    def initialize_schema(self) -> None:
        if not self.connection:
            raise RuntimeError(
                "Database connection has not been established."
            )

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs_raw (
                scrape_timestamp TIMESTAMP,

                source_platform VARCHAR,
                source_search_url VARCHAR,

                linkedin_job_id VARCHAR,

                title VARCHAR,
                company VARCHAR,
                location VARCHAR,

                workplace_type VARCHAR,
                employment_type VARCHAR,

                salary VARCHAR,

                posting_date VARCHAR,

                job_url VARCHAR,

                description VARCHAR
            );
            """
        )

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs_current (
                linkedin_job_id VARCHAR PRIMARY KEY,

                source_platform VARCHAR,
                source_search_url VARCHAR,

                title VARCHAR,
                company VARCHAR,
                location VARCHAR,

                workplace_type VARCHAR,
                employment_type VARCHAR,

                salary VARCHAR,

                posting_date VARCHAR,

                job_url VARCHAR,

                description VARCHAR,

                first_seen TIMESTAMP,
                last_seen TIMESTAMP
            );
            """
        )