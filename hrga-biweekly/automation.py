import os
import sys
import pandas as pd
import duckdb
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from core.config import biweeklyHrgaConfig
from core.cps import login_to_cps, download_po
from core.synology import get_synology_connection, ensure_synology_path, upload_to_synology_direct

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

def filter_and_export_hrga_po(input_path: str, output_path: str):
    """
    Loads the PO Entry list, applies HRGA specific filters using DuckDB,
    and exports the result to an Excel file.
    """
    print(f"Applying HRGA filter to {input_path}...")
    safe_input_path = input_path.replace('\\', '/')
    # Load via pandas to bypass DuckDB Excel extension versioning issues
    df = pd.read_excel(input_path)
    # Dynamic calculation: Find the most recent Wednesday as the end_date
    # weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    now = datetime.now()
    
    # Check for manual overrides via environment variables
    override_start = os.getenv("HRGA_START_DATE")
    override_end = os.getenv("HRGA_END_DATE")
    
    if override_start and override_end:
        start_date = pd.to_datetime(override_start).date()
        end_date = pd.to_datetime(override_end).date()
        print(f"Using manual override window: {start_date} to {end_date}")
    else:
        days_since_wed = (now.weekday() - 2) % 7
        end_date = (now - pd.Timedelta(days=days_since_wed)).date()
        # A full 2-week cycle from Thursday to Wednesday inclusive is exactly 13 days back from Wednesday
        start_date = end_date - pd.Timedelta(days=13)
        print(f"Dynamically calculated window (Thursday to Wednesday): {start_date} to {end_date}")

    con = duckdb.connect()
    con.register('raw_po', df)
    
    query = f"""
    SELECT *
    FROM raw_po
    WHERE Department ILIKE '%HRGA%' 
      AND Department NOT LIKE 'MMS%' 
      AND Department NOT LIKE 'AMS%' 
      AND Department NOT LIKE 'SLI%'
      AND try_cast("PO Approval Date" AS DATE) BETWEEN DATE '{start_date}' AND DATE '{end_date}'
    """
    
    filtered_df = con.query(query).df()
    print(f"Filtered down to {len(filtered_df)} HRGA PO records.")
    
    # Format dates in pandas if necessary, or just export directly
    filtered_df.to_excel(output_path, index=False)
    print(f"Successfully exported filtered data to {output_path}")
    con.close()
    return output_path

def main():
    print("=== Starting HRGA Biweekly Pipeline ===")
    
    # 1. Scrape the PO Entry List
    os.makedirs(biweeklyHrgaConfig.DOWNLOAD_DIR, exist_ok=True)
    
    po_path = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print("Logging into CPS...")
            login_to_cps(page, config=biweeklyHrgaConfig)
            
            print("Downloading PO Entry List...")
            po_path = download_po(page, config=biweeklyHrgaConfig)
        except Exception as e:
            print(f"Error during scraping: {e}")
            sys.exit(1)
        finally:
            browser.close()
            
    if not po_path or not os.path.exists(po_path):
        print("Failed to download PO Entry List. Aborting.")
        sys.exit(1)
        
    # 2. Filter and Export
    now = datetime.now()
    month = now.month
    date_str = now.strftime("%d%m%Y")
    
    filename = f"{month}. PO Entry List {date_str}.xlsx"
    export_path = os.path.join(biweeklyHrgaConfig.DOWNLOAD_DIR, filename)
    
    filter_and_export_hrga_po(po_path, export_path)
    
    # 3. Upload to Synology
    year_str = str(now.year)
    target_dir = f"{biweeklyHrgaConfig.BIWEEKLY_HRGA_PATH}/{year_str}"
    print(f"Connecting to Synology to upload directly to root year path: {target_dir}...")
    try:
        fl = get_synology_connection()
        
        # Proactively verify/create just the root year folder inside the base path
        try:
            check = fl.get_file_list(folder_path=biweeklyHrgaConfig.BIWEEKLY_HRGA_PATH)
            if 'data' in check and 'files' in check['data']:
                existing_folders = [f['name'] for f in check['data']['files']]
                if year_str not in existing_folders:
                    print(f"Creating year folder {year_str} inside {biweeklyHrgaConfig.BIWEEKLY_HRGA_PATH}")
                    fl.create_folder(folder_path=biweeklyHrgaConfig.BIWEEKLY_HRGA_PATH, name=year_str)
        except Exception as fold_err:
            print(f"Note on root folder check: {fold_err}")
            
        upload_to_synology_direct(export_path, target_dir, fl)
        print("Upload successful!")
    except Exception as e:
        print(f"Error during Synology upload: {e}")
        sys.exit(1)

    print("=== HRGA Biweekly Pipeline Completed Successfully ===")

if __name__ == "__main__":
    main()
