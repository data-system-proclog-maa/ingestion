# GEMINI.md

## Project Context
**Ingestion Pipeline**: A Python-based ELT/ETL framework designed for procurement and logistics data reconciliation. 
- **Data Flow**: Web Scraping (Playwright) -> Raw Storage (Parquet/Excel) -> Processing (DuckDB) -> Warehousing (BigQuery, PostgreSQL, Synology NAS).
- **Core Domains**: Purchase Orders (PO), Requisition for Materials (RFM), Transfer Lists (TL).

## Standards
- **Transformations**: Prefer DuckDB SQL for data transformations. It is significantly faster than pure Pandas for large datasets.
- **Parallelism**: Use `concurrent.futures.ThreadPoolExecutor` for database sync tasks (BQ/Postgres) to improve throughput.
- **Layers**: 
    - **Silver**: DuckDB-based cleaning and joining (e.g., `po_processed`).
    - **Gold**: Business-level aggregations (e.g., `gold_logistics_summary`).
- **Database Interops**: 
    - Use `core/bigquery.py` for Google BigQuery syncs. 
    - Use `core/postgres.py` with the `psql_insert_copy` method for high-performance PostgreSQL inserts (Serving DB: Neon).
- **Scraping**: Utilize the modular patterns in `core/cps.py` and `core/scrapefunction.py`. Always handle browser contexts cleanly with Playwright.
- **Naming Conventions**: 
    - Standardize dataframe columns using the utility logic in `core/bigquery.py` (replace spaces, slashes, and dashes with underscores).
    - Database table columns should generally be `lowercase_snake_case`.
- **Configuration**: Strictly use `core/config.py` and `.env` files for environment-specific variables. Never hardcode credentials. Use toggles like `USE_BIGQUERY` to enable/disable specific pipeline modules.

## Constraints
- **Python Runtime**: Minimum Python 3.10.
- **Concurrency**: Use `max_workers` configuration (default 1) to avoid resource exhaustion on the Synology NAS or Cloudflare-protected sites.
- **Internal Storage**: Raw `.xlsx` files must be converted to `.parquet` before processing to ensure high-performance DuckDB views.
- **Schema Management**: 
    - In BigQuery, use `autodetect=True` for evolving schemas unless strict validation is required.
    - Intermediate files should be stored as `.parquet` to preserve data types.
- **Path Handling**: Use `os.path.join` or `Pathlib` for cross-platform compatibility (Windows development, Linux CI/CD).
