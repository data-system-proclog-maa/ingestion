import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # put this on top of the file, before importing other module

import pandas as pd
from dotenv import load_dotenv

import json

from google.oauth2 import service_account
from google.cloud import bigquery


from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import dailyScrapperConfig
from core.cps import login_to_cps
from core.synology import get_synology_connection, daily_upload_to_synology
from core.bigquery import upload_to_bq
from core.scrapefunction import login_to_cps_mobile, scrape_po_receive, scrape_tl_receive, scrape_inventory




# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()


#setting up gcp credentials
if os.getenv("GCP_SA_KEY"):
    # for actions
    gcp_sa_info = json.loads(os.getenv("GCP_SA_KEY"))
else:
    # for local
    with open (os.path.join(BASE_DIR, dailyScrapperConfig.GCP_SA_KEY), "r", encoding="utf-8") as f:
        gcp_sa_info = json.load(f)

credentials = service_account.Credentials.from_service_account_info(gcp_sa_info)
bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)

def main():
    # creating folder
    if not os.path.exists(dailyScrapperConfig.DOWNLOAD_DIR):
        os.makedirs(dailyScrapperConfig.DOWNLOAD_DIR)

    po_r_path = tl_r_path = None

    sync_registry = {} #changed to dict for easy tracking multiple file

    try:
        with sync_playwright() as p:
            # headless tracking, change to False for debugging
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = browser.new_page()
            
            try:
                login_to_cps_mobile(context)
                # 1. scrape po receive
                po_receive_df = scrape_po_receive(context, 1, 18200)
                
                # Sync to BQ
                if bq_client:
                    try:
                        table_id = f"{bq_client.project}.{dailyScrapperConfig.BQ_DATASET}.{dailyScrapperConfig.BQ_TABLE_PO_R}"
                        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
                        job = bq_client.load_table_from_dataframe(po_receive_df, table_id, job_config=job_config)
                        job.result()
                        print(f"synced PO receive to BQ: {table_id}")
                    except Exception as e:
                        print(f"failed to sync PO receive to BQ: {e}")

                # Save to parquet for Synology - > was from csv
                po_receive_loc = os.path.join(dailyScrapperConfig.DOWNLOAD_DIR, "po_receive_data.parquet")
                po_receive_df.to_parquet(po_receive_loc)
                sync_registry["po_receive"] = po_receive_loc


                # 2. scrape tl receive
                tl_receive_df = scrape_tl_receive(context, 1, 4105)
                
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

                # Save to parquet for Synology - > was from csv
                tl_receive_loc = os.path.join(dailyScrapperConfig.DOWNLOAD_DIR, "tl_receive_data.parquet")
                tl_receive_df.to_parquet(tl_receive_loc)
                sync_registry["tl_receive"] = tl_receive_loc

            #     # 3. scrape inventory handover
            #     inventory_handover_df = scrape_inventory(context, 100, 110)
                
            #     # Sync to BQ
            #     if bq_client:
            #         try:
            #             table_id = f"{bq_client.project}.{dailyScrapperConfig.BQ_DATASET}.{dailyScrapperConfig.BQ_TABLE_INVENTORY_HO}"
            #             job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True)
            #             job = bq_client.load_table_from_dataframe(inventory_handover_df, table_id, job_config=job_config)
            #             job.result()
            #             print(f"Synced Inventory Handover to BQ: {table_id}")
            #         except Exception as e:
            #             print(f"Failed to sync Inventory Handover to BQ: {e}")

            #     # Save to CSV for Synology
            #     inventory_handover_csv = os.path.join(dailyScrapperConfig.DOWNLOAD_DIR, "inventory_handover_data.csv")
            #     inventory_handover_df.to_csv(inventory_handover_csv, index=False)
            #     sync_registry["inventory_handover"] = inventory_handover_csv

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