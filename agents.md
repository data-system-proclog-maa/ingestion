# AGENTS.md

## 🕵️ Scraper Agent
**Focus**: Web Automation & Extraction
- **Scope**: `core/cps.py`, `core/scrapefunction.py`, `daily/automation.py` (scraping block).
- **Core Skill**: Playwright selector stability, wait-state management, and handling download events.
- **Principle**: Always ensure `headless=True` for production but allow `headless=False` for local debugging. Use generic, reusable scraping functions from `core/`.

## 🛠️ Transformer Agent (DuckDB Specialist)
**Focus**: Data Processing & Silver/Gold Layer Logic
- **Scope**: `daily/transform/`
- **Core Skill**: Writing highly optimized DuckDB SQL for data cleaning, joining, and aggregation. 
- **Principle**: Avoid Pandas `for` loops. Use `con.query()` or views. Ensure type safety by using `try_cast` and handling nulls early in the Silver layer.

## 🚀 Sync Agent (Data Warehousing)
**Focus**: Database Throughput & Schema Integrity
- **Scope**: `core/bigquery.py`, `core/postgres.py`, `core/motherduck.py`, `core/synology.py`
- **Core Skill**: BigQuery `job_config`, Postgres `COPY` performance, MotherDuck integration, Synology API authentication, and Motherduck `md:` protocol.
- **Principle**: Minimize I/O by using `.parquet`. Handle schema evolution gracefully. Use threading to parallelize uploads to multiple destinations.

## 🏗️ Orchestrator Agent
**Focus**: Pipeline Reliability & Config Management
- **Scope**: `daily/automation.py`, `core/config.py`, `.env`
- **Core Skill**: Dependency management, error handling/retry logic, and cross-platform pathing.
- **Principle**: Ensure the main loop in `automation.py` is clean, logs progress clearly, and handles failure at any stage without corrupting subsequent steps.
