from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Job(BaseModel):
    scrape_timestamp: datetime

    source_platform: str
    source_search_url: str

    linkedin_job_id: str

    title: str
    company: str
    location: Optional[str] = None

    workplace_type: Optional[str] = None
    employment_type: Optional[str] = None

    salary: Optional[str] = None

    posting_date: Optional[str] = None

    job_url: str

    description: Optional[str] = None

    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None