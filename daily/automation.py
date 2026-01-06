import os
import sys
import pandas as pd
from dotenv import load_dotenv
import json

from google.oauth2 import service_account
from google.cloud import bigquery

from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import dailyConfig
from core.cps import login_to_cps, download_rfm_tl, download_po
from core.synology import get_synology_connection, daily_upload_to_synology
from core.bigquery import upload_to_bq

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

#setting up gcp credentials
if os.getenv("GCP_SA_KEY"):
    # for actions
    gcp_sa_info = json.loads(os.getenv("GCP_SA_KEY"))
else:
    # for local
    with open (dailyConfig.GCP_SA_KEY, "r", encoding="utf-8") as f:
        gcp_sa_info = json.load(f)

credentials = service_account.Credentials.from_service_account_info(gcp_sa_info)
bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)

def main():
    # creating folder
    if not os.path.exists(dailyConfig.DOWNLOAD_DIR):
        os.makedirs(dailyConfig.DOWNLOAD_DIR)

    rfm_path = tl_path = po_path = None

    sync_registry = {} #changed to dict for easy tracking multiple file

    try:
        with sync_playwright() as p:
            # headless tracking, change to False for debugging
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                login_to_cps(page)
                
                # 1. download rfm
                rfm_path = download_rfm_tl(
                    page, 
                    "https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_RequisitionEntryList.aspx", 
                    "Requisition Entry List.xlsx"
                )
                sync_registry["rfm"] = rfm_path
                
                # 2. download tl
                tl_path = download_rfm_tl(
                    page,
                    "https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_TransferList.aspx",
                    "Transfer List.xlsx",
                    export_selector="#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_mnuNAV_DXI6_PImg"
                )
                sync_registry["tl"] = tl_path
                
                # 3. download po
                po_path = download_po(page)
                sync_registry["po"] = po_path
                
            finally:
                browser.close()

        bq_sync_map = {
            rfm_path: dailyConfig.BQ_TABLE_RFM,
            tl_path: dailyConfig.BQ_TABLE_TL,
            po_path: dailyConfig.BQ_TABLE_PO
        }
        DATASET_ID = dailyConfig.BQ_DATASET
        # sync to bq
        if sync_registry:
            print("\nStarting BQ Sync...")
            for file_path, table in bq_sync_map.items():
                if file_path and table:
                    try:
                        upload_to_bq(bq_client, file_path, table, DATASET_ID)
                    except Exception as e:
                        print(f"failed to sync {file_path} to BQ: {e}")
                    else:
                        print(f"synced {file_path} to BQ: {table}")

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
