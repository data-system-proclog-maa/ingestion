# Ingestion Pipeline

## Overview
This repository hosts the data ingestion pipelines for the ETL process. It automates the extraction of data from various sources (CPS, OnlinePO) and syncs it to Google BigQuery and the Synology NAS.

## Folder Structure
- **`daily/`**: Production-ready scripts for daily data ingestion.
    - `automation.py`: Main script for downloading reports (PO, RFM, TL) and syncing them.
- **`weekly/`**: Intended for weekly data aggregation and reporting.
    - `weekly_report.py`: Main script for downloading reports (PO, RFM), then processing it and syncing it to Synology
- **`.github/workflows/`**: CI/CD configurations for automated runs.

## Setup & Installation

### Prerequisites
- Python 3.10+
- Google Cloud Service Account (for BigQuery)
- Synology NAS Credentials

### Local Development
1.  **Clone the repository**:
    ```bash
    git clone <repo-url>
    cd ingestion
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r daily/requirements.txt
    playwright install chromium
    ```

3.  **Environment Variables**:
    Create a `.env` file in `daily/` (or set system variables) with the following:
    ```ini
    CPS_USERNAME=your_username
    CPS_PASSWORD=your_password
    NAS_DOMAIN=nas.example.com
    NAS_USERNAME=synology_user
    NAS_PASSWORD=synology_pass
    DAILY_PATH=/path/to/daily/folder
    BQ_DATASET=your_dataset
    BQ_TABLE_PO=table_po
    BQ_TABLE_RFM=table_rfm
    BQ_TABLE_TL=table_tl
    GCP_SA_KEY={"type": "service_account", ...} # JSON content of your key
    ```

## Usage
To run the daily ingestion manually:
```bash
python daily/automation.py
```

## Maintenance Guide

### 1. Adding New Reports
To download a new report type:
1.  Open `daily/automation.py`.
2.  Add a new download function (e.g., `download_new_report(page)`).
3.  Call it inside the `main()` function's `sync_playwright` block.
4.  Add the new file path to `bq_sync_map` and provide a corresponding BigQuery table name in `Config`.

### 2. Updating BigQuery Schema
The script uses `autodetect=True` and `WRITE_TRUNCATE`.
- If the source file columns change, BigQuery will attempt to adapt.
- If you need strict schema control, modify the `job_config` in `upload_to_bq` to use a defined schema.

### 3. Debugging Failures
- **Login Issues**: Check `CPS_USERNAME`/`PASSWORD`. Run with `headless=False` locally to watch the browser flow.
- **Timeout Errors**: Increase `page.wait_for_timeout()` or usages of `expect_download(timeout=...)`.
- **BigQuery Errors**: ensure `GCP_SA_KEY` has the correct `BigQuery Data Editor` permissions.

## License
MIT License. See [LICENSE](LICENSE) for details.
