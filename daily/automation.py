import os
import sys
import pandas as pd
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json

from google.oauth2 import service_account
from google.cloud import bigquery

from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import dailyConfig
from core.cps import login_to_cps, download_rfm_tl, download_po
from core.synology import get_synology_connection, daily_upload_to_synology
from core.bigquery import upload_to_bq, load_dataframe_to_bq
from core.postgres import upload_to_postgres, load_dataframe_to_postgres
from daily.transform.silver_po import transform_po_silver
from daily.transform.silver_rfm import transform_rfm_silver
from daily.transform.gold_logistics_summary import transform_gold_logistics


# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

#setting up gcp credentials
if os.getenv("GCP_SA_KEY"):
    # for actions
    gcp_sa_info = json.loads(os.getenv("GCP_SA_KEY"))
else:
    # for local
    with open (os.path.join(BASE_DIR, dailyConfig.GCP_SA_KEY), "r", encoding="utf-8") as f:
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

        # --- PRE-PROCESS: Convert Excel to Parquet for Speed ---
        parquet_sync_map = {}
        if sync_registry:
            print("\nConverting Excel to Parquet for internal speed (Parallel)...")
            import concurrent.futures

            def convert_to_parquet(key_path_tuple):
                key, excel_path = key_path_tuple
                if excel_path and excel_path.endswith('.xlsx'):
                    pq_path = excel_path.replace('.xlsx', '.parquet')
                    try:
                        df = pd.read_excel(excel_path)
                        # Clean column names immediately so Parquet is native-ready for DuckDB
                        df.columns = [
                            c.replace(' ', '_').replace('/', '_').replace('-', '_').replace('%', 'pct') 
                            for c in df.columns
                        ]
                        df.to_parquet(pq_path)
                        return key, excel_path, pq_path
                    except Exception as e:
                        print(f"Failed to convert {key} to Parquet: {e}")
                return None

            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = executor.map(convert_to_parquet, sync_registry.items())
                for res in results:
                    if res:
                        key, excel_path, pq_path = res
                        parquet_sync_map[excel_path] = pq_path
                        print(f"Converted {key} to Parquet.")

        # --- MASTER PROCESSING LAYER ---
        processed_rfm_df = None
        processed_po_df = None
        
        if rfm_path:
            transform_rfm_path = parquet_sync_map.get(rfm_path, rfm_path)
            
            print("\nStarting DuckDB Transformation for RFM List...")
            try:
                processed_rfm_df = transform_rfm_silver(transform_rfm_path)
            except Exception as e:
                print(f"Failed to transform RFM: {e}")

        if po_path:
            # Use the Parquet version if available
            transform_po_path = parquet_sync_map.get(po_path, po_path)
            transform_tl_path = parquet_sync_map.get(tl_path, tl_path)
            
            print("\nStarting DuckDB Transformation for PO List...")
            try:
                processed_po_df = transform_po_silver(transform_po_path, transform_tl_path, processed_rfm_df)
            except Exception as e:
                print(f"Failed to transform PO: {e}")

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
                    # Use Parquet path for BQ upload if it exists
                    upload_path = parquet_sync_map.get(file_path, file_path)
                    try:
                        upload_to_bq(bq_client, upload_path, table, DATASET_ID)
                    except Exception as e:
                        print(f"failed to sync {file_path} to BQ: {e}")
                    else:
                        print(f"synced {file_path} to BQ: {table}")

            # Sync Processed table to BQ
            if processed_po_df is not None:
                processed_table = "po_processed"
                try:
                    load_dataframe_to_bq(bq_client, processed_po_df, processed_table, DATASET_ID)
                except Exception as e:
                    print(f"failed to sync Master Processed PO to BQ: {e}")

            if processed_rfm_df is not None:
                try:
                    load_dataframe_to_bq(bq_client, processed_rfm_df, "rfm_processed", DATASET_ID)
                except Exception as e:
                    print(f"failed to sync Master Processed RFM to BQ: {e}")

                # --- GOLD LAYER: Logistics Summary ---
                print("\nStarting Gold Transformation for Logistics Summary...")
                try:
                    gold_logistics_df = transform_gold_logistics(processed_po_df)
                    if gold_logistics_df is not None:
                        load_dataframe_to_bq(bq_client, gold_logistics_df, "gold_logistics_summary", DATASET_ID)
                except Exception as e:
                    print(f"Failed to transform/sync Gold Logistics to BQ: {e}")

        # sync to postgres
        if sync_registry and dailyConfig.SERVING_DB:
            print("\nStarting Postgres (Neon) Sync...")
            try:
                from sqlalchemy import create_engine
                from core.postgres import upload_to_postgres
                
                engine = create_engine(dailyConfig.SERVING_DB)
                for file_path, table in bq_sync_map.items():
                    if file_path and table:
                        # Use Parquet path for Postgres upload if it exists
                        upload_path = parquet_sync_map.get(file_path, file_path)
                        try:
                            # Load to public schema, replacing existing table
                            upload_to_postgres(engine, upload_path, table)
                        except Exception as e:
                            print(f"Failed to sync {file_path} to Postgres: {e}")

                # Sync Master Processed table to Postgres
                if processed_po_df is not None:
                    processed_table = "po_processed"
                    try:
                        load_dataframe_to_postgres(engine, processed_po_df, processed_table)
                    except Exception as e:
                        print(f"Failed to sync Master Processed PO to Postgres: {e}")

                if processed_rfm_df is not None:
                    try:
                        load_dataframe_to_postgres(engine, processed_rfm_df, "rfm_processed")
                    except Exception as e:
                        print(f"Failed to sync Master Processed RFM to Postgres: {e}")

                # Sync Gold Logistics table to Postgres
                if 'gold_logistics_df' in locals() and gold_logistics_df is not None:
                    try:
                        load_dataframe_to_postgres(engine, gold_logistics_df, "gold_logistics_summary")
                    except Exception as e:
                        print(f"Failed to sync Gold Logistics to Postgres: {e}")

            except ImportError:
                print("SQLAlchemy or Psycopg2 not installed. Skipping Postgres sync.")
            except Exception as e:
                print(f"Postgres connection error: {e}")

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
