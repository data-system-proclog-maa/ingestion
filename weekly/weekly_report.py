import os
import sys
import pandas as pd
from dotenv import load_dotenv

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import weeklyConfig
from core.cps import login_to_cps, download_rfm_tl, download_po
from core.synology import get_synology_connection, weekly_upload_to_synology

from app.main import run as run_processor #pulling the file from git

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

def get_weekly_dates():
    end_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
    start_dt = end_dt - timedelta(days=7)
    return start_dt.strftime("%d-%m-%Y"), end_dt.strftime("%d-%m-%Y")

def main():
    # creating folder
    if not os.path.exists(weeklyConfig.DOWNLOAD_DIR):
        os.makedirs(weeklyConfig.DOWNLOAD_DIR)

    rfm_path = po_path = None

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
                
                # 2. download po
                po_path = download_po(page)
                sync_registry["po"] = po_path
                
            finally:
                browser.close()

        # run processor
        start_str, end_str = get_weekly_dates()
        print(f"Current Jakarta Time: {datetime.now(ZoneInfo('Asia/Jakarta')).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Processing Range: {start_str} to {end_str}")     

        processed_output = run_processor(
            po_file = sync_registry["po"],
            rfm_file = sync_registry["rfm"],
            start_date = start_str,
            end_date = end_str,
            output_dir = weeklyConfig.DOWNLOAD_DIR
        ) 

        sync_registry["rfm_processed"] = processed_output['rfm_output_path']
        sync_registry["po_processed"] = processed_output['po_output_path']


        # sync to synology
        if sync_registry:
            print("\nStarting Synology Sync to Weekly Folder...")
            fl = get_synology_connection()
            for key, file_path in sync_registry.items():
                if file_path and os.path.exists(file_path):
                    print(f"Uploading {key}: {file_path}")
                    weekly_upload_to_synology(file_path, fl)

    except Exception as e:
        print(f"Critical Automation Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
