import os
import sys
import pandas as pd
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import traceback

from google.oauth2 import service_account
from google.cloud import bigquery

from playwright.sync_api import sync_playwright
from synology_api.filestation import FileStation

from core.config import dailyConfig
from core.cps import login_to_cps, download_rfm_tl, download_po
from core.synology import get_synology_connection, ensure_synology_path, upload_to_synology_direct
from core.bigquery import upload_to_bq, load_dataframe_to_bq
from core.postgres import upload_to_postgres, load_dataframe_to_postgres
from daily.transform.silver_po import transform_po_silver
from daily.transform.silver_rfm import transform_rfm_silver
from daily.transform.gold_logistics_summary import transform_gold_logistics


# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

# setting up gcp credentials (if enabled)
bq_client = None
if dailyConfig.USE_BIGQUERY:
    if os.getenv("GCP_SA_KEY"):
        # for actions
        gcp_sa_info = json.loads(os.getenv("GCP_SA_KEY"))
    else:
        # for local
        gcp_key_path = os.path.join(BASE_DIR, dailyConfig.GCP_SA_KEY)
        if os.path.exists(gcp_key_path):
            with open (gcp_key_path, "r", encoding="utf-8") as f:
                gcp_sa_info = json.load(f)
        else:
            print("Warning: GCP_SA_KEY file not found. BigQuery initialization skipped.")
            gcp_sa_info = None

    if gcp_sa_info:
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
                    dailyConfig.URL_RFM_LIST, 
                    "Requisition Entry List.xlsx"
                )
                sync_registry["rfm"] = rfm_path
                
                # 2. download tl
                tl_path = download_rfm_tl(
                    page,
                    dailyConfig.URL_TL_LIST,
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
            # 1. Pre-load DuckDB extensions in the main thread to avoid concurrency locks
            import duckdb
            print("\nInitializing DuckDB extensions...")
            try:
                con = duckdb.connect()
                print("Installing/Loading DuckDB extensions (spatial, excel)...")
                con.execute("INSTALL spatial; LOAD spatial;")
                con.execute("INSTALL excel; LOAD excel;")
                con.close()
                print("DuckDB extensions initialized.")
            except Exception as e:
                print(f"Warning: DuckDB extension setup encountered an issue: {e}. The script will try to use fallbacks.")

            print("Converting Excel to Parquet for internal speed (Parallel)...")
            import concurrent.futures

            def convert_to_parquet(key_path_tuple):
                key, excel_path = key_path_tuple
                if not excel_path or not excel_path.endswith('.xlsx'):
                    return None
                    
                pq_path = excel_path.replace('.xlsx', '.parquet')
                try:
                    import duckdb
                    con = duckdb.connect()
                    
                    # 1. Proactively find a working Excel reader
                    reader_func = None
                    # Try excel extension first
                    try:
                        con.execute("INSTALL excel; LOAD excel;")
                        con.execute(f"SELECT * FROM read_excel('{excel_path}') LIMIT 0")
                        reader_func = "read_excel"
                    except:
                        # Try spatial fallback
                        try:
                            con.execute("INSTALL spatial; LOAD spatial;")
                            con.execute(f"SELECT * FROM st_read('{excel_path}') LIMIT 0")
                            reader_func = "st_read"
                        except:
                            con.close()
                            raise ImportError("No working DuckDB Excel reader found (tried read_excel and st_read).")
                    
                    # 2. Get raw column names using the verified reader
                    temp_view = f"temp_{key}"
                    con.execute(f"CREATE OR REPLACE VIEW {temp_view} AS SELECT * FROM {reader_func}('{excel_path}') LIMIT 0")
                    raw_cols = [col[0] for col in con.execute(f"DESCRIBE {temp_view}").fetchall()]
                    
                    # 3. Map cleaned names
                    select_parts = []
                    for col in raw_cols:
                        clean = col.replace(' ', '_').replace('/', '_').replace('-', '_').replace('%', 'pct')
                        select_parts.append(f'"{col}" AS "{clean}"')
                    
                    select_sql = ", ".join(select_parts)
                    
                    # 4. Export to Parquet (High performance)
                    print(f"DuckDB ({reader_func}) converting {key} to Parquet...")
                    con.execute(f"COPY (SELECT {select_sql} FROM {reader_func}('{excel_path}')) TO '{pq_path}' (FORMAT 'PARQUET')")
                    con.close()
                    return key, excel_path, pq_path
                except Exception as e:
                    print(f"Failed to convert {key} to Parquet via DuckDB: {e}")
                    # Fallback to pandas
                    try:
                        import pandas as pd
                        df = pd.read_excel(excel_path)
                        df.columns = [c.replace(' ', '_').replace('/', '_').replace('-', '_').replace('%', 'pct') for c in df.columns]
                        df.to_parquet(pq_path)
                        return key, excel_path, pq_path
                    except Exception as e2:
                        print(f"Final fallback failed for {key}: {e2}")
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
                if processed_rfm_df is None:
                    raise ValueError("RFM Silver transformation returned empty results.")
            except Exception as e:
                print(f"CRITICAL ERROR: Failed to transform RFM: {e}")
                sys.exit(1) # Circuit Breaker

        if po_path:
            # Use the Parquet version if available
            transform_po_path = parquet_sync_map.get(po_path, po_path)
            transform_tl_path = parquet_sync_map.get(tl_path, tl_path)
            
            print("\nStarting DuckDB Transformation for PO List...")
            try:
                processed_po_df = transform_po_silver(transform_po_path, transform_tl_path, processed_rfm_df)
                if processed_po_df is None:
                    raise ValueError("PO Silver transformation returned empty results.")
            except Exception as e:
                print(f"CRITICAL ERROR: Failed to transform PO: {e}")
                sys.exit(1) # Circuit Breaker

        # --- GOLD LAYER: Logistics Summary ---
        gold_logistics_df = None
        if processed_po_df is not None:
            print("\nStarting Gold Transformation for Logistics Summary...")
            try:
                gold_logistics_df = transform_gold_logistics(processed_po_df)
                if gold_logistics_df is None:
                    raise ValueError("Gold Logistics transformation returned empty results.")
            except Exception as e:
                print(f"CRITICAL ERROR: Failed to transform Gold Logistics: {e}")
                sys.exit(1) # Circuit Breaker

        # --- INGESTION LOG ---
        print("\nCreating Ingestion Log...")
        import datetime
        gmt7 = datetime.timezone(datetime.timedelta(hours=7))
        ingestion_log_df = pd.DataFrame({
            'date_updated': [datetime.datetime.now(gmt7).replace(tzinfo=None)]
        })

        bq_sync_map = {
            rfm_path: dailyConfig.BQ_TABLE_RFM,
            tl_path: dailyConfig.BQ_TABLE_TL,
            po_path: dailyConfig.BQ_TABLE_PO
        }
        DATASET_ID = dailyConfig.BQ_DATASET
        
        # sync to bq (if enabled)
        if sync_registry and dailyConfig.USE_BIGQUERY and bq_client:
            print("\nStarting BQ Sync (Parallel)...")
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                bq_futures = []
                for file_path, table in bq_sync_map.items():
                    if file_path and table:
                        upload_path = parquet_sync_map.get(file_path, file_path)
                        bq_futures.append(executor.submit(upload_to_bq, bq_client, upload_path, table, DATASET_ID))

                # Sync Processed tables to BQ
                if processed_po_df is not None:
                    bq_futures.append(executor.submit(load_dataframe_to_bq, bq_client, processed_po_df, "po_processed", DATASET_ID))
                if processed_rfm_df is not None:
                    bq_futures.append(executor.submit(load_dataframe_to_bq, bq_client, processed_rfm_df, "rfm_processed", DATASET_ID))
                if gold_logistics_df is not None:
                    bq_futures.append(executor.submit(load_dataframe_to_bq, bq_client, gold_logistics_df, "gold_logistics_summary", DATASET_ID))
                
                # Sync Ingestion Log
                bq_futures.append(executor.submit(load_dataframe_to_bq, bq_client, ingestion_log_df, "ingestion_log", DATASET_ID))

                for future in concurrent.futures.as_completed(bq_futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"CRITICAL ERROR: BQ sync task failed: {e}")
                        sys.exit(1) # Stop immediately if warehouse sync fails
        elif not dailyConfig.USE_BIGQUERY:
            print("\nBigQuery sync is currently DEACTIVATED in config.")

        # sync to postgres
        if sync_registry and dailyConfig.SERVING_DB:
            print("\nStarting Postgres (Neon) Sync (Parallel)...")
            try:
                from sqlalchemy import create_engine
                from core.postgres import upload_to_postgres
                
                engine = create_engine(dailyConfig.SERVING_DB)
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    pg_futures = []
                    for file_path, table in bq_sync_map.items():
                        if file_path and table:
                            upload_path = parquet_sync_map.get(file_path, file_path)
                            pg_futures.append(executor.submit(upload_to_postgres, engine, upload_path, table))

                    # Sync Master Processed tables to Postgres
                    if processed_po_df is not None:
                        pg_futures.append(executor.submit(load_dataframe_to_postgres, engine, processed_po_df, "po_processed"))
                    if processed_rfm_df is not None:
                        pg_futures.append(executor.submit(load_dataframe_to_postgres, engine, processed_rfm_df, "rfm_processed"))
                    if gold_logistics_df is not None:
                        pg_futures.append(executor.submit(load_dataframe_to_postgres, engine, gold_logistics_df, "gold_logistics_summary"))
                    
                    # Sync Ingestion Log
                    pg_futures.append(executor.submit(load_dataframe_to_postgres, engine, ingestion_log_df, "ingestion_log"))
                    
                    for future in concurrent.futures.as_completed(pg_futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"CRITICAL ERROR: Postgres sync task failed: {e}")
                            sys.exit(1) # Stop immediately if serving DB sync fails

            except ImportError:
                print("SQLAlchemy or Psycopg2 not installed. Skipping Postgres sync.")
            except Exception as e:
                print(f"Postgres connection error: {e}")

        # sync to synology
        if sync_registry:
            print("\nStarting Synology Sync...")
            import time
            try:
                fl = get_synology_connection()
                # 1. Verify path once
                target_dir = ensure_synology_path(fl, dailyConfig.DAILY_PATH)
                
                # 2. Upload all files
                for file_path in sync_registry.values():
                    if file_path and os.path.exists(file_path):
                        upload_to_synology_direct(file_path, target_dir, fl)
                        time.sleep(2) # Small pause to let NAS breathe
                    else:
                        print(f"Skipping Synology upload for missing file: {file_path}")
            except Exception as e:
                print(f"Synology Sync encountered a non-critical issue: {e}")
                # We don't sys.exit here because the data is already in DBs

    except Exception as e:
        print(f"Critical Automation Error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
