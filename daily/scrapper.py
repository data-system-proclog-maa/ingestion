import os
import sys
# add project root to PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
import json

from google.oauth2 import service_account
from google.cloud import bigquery


from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import dailyScrapperConfig
from core.cps import login_to_cps
from core.synology import get_synology_connection, daily_upload_to_synology
from core.bigquery import upload_to_bq
from core.scrapefunction import scrape_po_receive_data, scrape_tl_receive_data



# --- resolve paths correctly ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if os.getenv("GCP_SA_KEY"):
    # GitHub Actions / CI
    gcp_sa_info = json.loads(os.getenv("GCP_SA_KEY"))
else:
    # Local dev
    gcp_key_path = os.path.join(BASE_DIR, dailyScrapperConfig.GCP_SA_KEY)

    if not os.path.exists(gcp_key_path):
        raise FileNotFoundError(f"GCP key not found at: {gcp_key_path}")

    with open(gcp_key_path, "r", encoding="utf-8") as f:
        gcp_sa_info = json.load(f)

credentials = service_account.Credentials.from_service_account_info(gcp_sa_info)
bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)

def main():
    print("Script started...")
    # creating folder
    if not os.path.exists(dailyScrapperConfig.DOWNLOAD_DIR):
        os.makedirs(dailyScrapperConfig.DOWNLOAD_DIR)

    po_r_path = tl_r_path = None

    sync_registry = {} #changed to dict for easy tracking multiple file

    try:
        with sync_playwright() as p:
            # headless tracking, change to False for debugging
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            
            try:
                # 1. scrape po receive
                po_receive_df = scrape_po_receive_data(page, 29875, 29881)
                
                # Sync to BQ
                if bq_client:
                    try:
                        table_id = f"{bq_client.project}.{dailyScrapperConfig.BQ_DATASET}.{dailyScrapperConfig.BQ_TABLE_PO_R}"
                        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
                        job = bq_client.load_table_from_dataframe(po_receive_df, table_id, job_config=job_config)
                        job.result()
                        print(f"Synced PO Receive to BQ: {table_id}")
                    except Exception as e:
                        print(f"Failed to sync PO Receive to BQ: {e}")

                # Save to CSV for Synology
                po_receive_csv = os.path.join(dailyScrapperConfig.DOWNLOAD_DIR, "po_receive_data.csv")
                po_receive_df.to_csv(po_receive_csv, index=False)
                sync_registry["po_receive"] = po_receive_csv


                # 2. scrape tl receive
                tl_receive_df = scrape_tl_receive_data(page, 7800, 7850)
                
                # Sync to BQ
                if bq_client:
                    try:
                        table_id = f"{bq_client.project}.{dailyScrapperConfig.BQ_DATASET}.{dailyScrapperConfig.BQ_TABLE_TL_R}"
                        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
                        job = bq_client.load_table_from_dataframe(tl_receive_df, table_id, job_config=job_config)
                        job.result()
                        print(f"Synced TL Receive to BQ: {table_id}")
                    except Exception as e:
                        print(f"Failed to sync TL Receive to BQ: {e}")

                # Save to CSV for Synology
                tl_receive_csv = os.path.join(dailyScrapperConfig.DOWNLOAD_DIR, "tl_receive_data.csv")
                tl_receive_df.to_csv(tl_receive_csv, index=False)
                sync_registry["tl_receive"] = tl_receive_csv

            finally:
                browser.close()

        # sync to synology
        if sync_registry:
            print("\nStarting Synology Sync...")
            fl = get_synology_connection()
            for file_path in sync_registry.values():
                daily_upload_to_synology(file_path, fl)

    except Exception as e:
        print(f"Critical Automation Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()