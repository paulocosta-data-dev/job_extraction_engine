# Job Extraction Engine

## Overview

Job Extraction Engine is a Python-based data engineering project designed to automatically extract, normalize and persist job opportunities from LinkedIn Jobs searches.

The project focuses on building a reliable extraction layer that can later feed a broader Career Operating System responsible for job evaluation, ranking, application tracking and career decision support.

Current scope:

* LinkedIn Jobs extraction
* Job normalization
* Historical storage
* CSV export

Out of scope:

* Job scoring
* AI summaries
* Cover letter generation
* Application tracking
* Recruiter tracking
* Dashboards

---

# Architecture

```text
LinkedIn Jobs Search
        ↓
Playwright
        ↓
Job Extraction
        ↓
Normalization
        ↓
DuckDB

    jobs_raw
    jobs_current

        ↓
CSV Export
```

## Design Principles

* Free and open-source technologies
* Production-oriented architecture
* Maintainability over complexity
* Historical tracking from day one
* Simple deployment
* GitHub portfolio quality

---

# Technology Stack

| Component          | Technology  |
| ------------------ | ----------- |
| Language           | Python 3.11 |
| Browser Automation | Playwright  |
| Validation         | Pydantic    |
| Storage            | DuckDB      |
| Export             | CSV         |

---

# Repository Structure

```text
job-extraction-engine/

├── README.md
├── ROADMAP.md
├── ARCHITECTURE.md
├── requirements.txt

├── profiles/
│   └── linkedin/

├── data/
│   ├── duckdb/
│   ├── exports/
│   └── logs/

├── src/
│   ├── main.py
│   ├── extraction/
│   ├── normalization/
│   ├── storage/
│   ├── export/
│   └── models/

└── tests/
```

---

# Setup

## Create Virtual Environment

```bash
python -m venv .venv
```

## Activate Virtual Environment

Windows CMD:

```bash
.venv\Scripts\activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Install Playwright Browser Support

```bash
python -m playwright install chrome
```

---

# First Login

The project uses a dedicated Playwright profile.

Profile location:

```text
profiles/linkedin/
```

On first execution:

1. Browser opens.
2. Login to LinkedIn manually.
3. Close browser.
4. Session is stored.

Subsequent executions reuse the stored session.

---

# Data Model

## jobs_raw

Stores every extraction event.

Purpose:

* Historical analysis
* Audit trail
* Change tracking

## jobs_current

Stores the latest known version of each job.

Purpose:

* Export generation
* Current opportunity analysis

---

# Current Status

Implemented:

* Project structure
* Environment setup
* Browser strategy
* Storage strategy
* Database schema design

In Progress:

* Browser initialization
* Search extraction

Planned:

* Job detail extraction
* Historical persistence
* CSV export

---

# Why This Project Exists

Most job searches are managed manually using spreadsheets, bookmarks and browser tabs.

This project treats job searching as a data engineering problem:

* Extract data automatically
* Persist historical records
* Normalize information
* Enable downstream analytics

The long-term objective is to provide structured data that can support informed career decisions rather than manual job tracking.

---

# Future Extensions

Not part of the extraction engine itself:

* Job ranking
* Opportunity scoring
* AI summaries
* Recruiter tracking
* Application tracking
* Career Operating System integration
