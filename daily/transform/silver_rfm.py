import duckdb
import os
import pandas as pd
from datetime import datetime
from core.config import dailyConfig
from core.transform_utils import register_silver_macros, init_duckdb_view, fetch_normalization_df

def transform_rfm_silver(raw_path):
    """
    Transforms RFM data using DuckDB.
    Supports both .xlsx and .parquet inputs.
    """
    # Initialize DuckDB
    con = duckdb.connect()

    # Load RFM data
    print(f"Reading RFM data from {raw_path}...")
    if not init_duckdb_view(con, raw_path, 'df_rfm'):
        con.close()
        return None

    # Register macros
    register_silver_macros(con)

    # Fetch Normalisasi Google Sheet
    print("Fetching RFM Normalisasi from Google Sheets...")
    url = dailyConfig.URL_RFM_NORMALISASI
    fetch_normalization_df(con, url, 'df_norm', ['Requisition Number', 'Updated Requisition Approved Date', 'Background Update'])

    query = r"""
    WITH cleaned_rfm AS (
        SELECT 
            *,
            clean_dept_or_project(Project) AS clean_project,
            translate_indo_months(Progress_Status) AS raw_pq_text
        FROM df_rfm
    ),
    rfm_with_base AS (
        SELECT 
            *,
            trim(split_part(split_part(clean_project, '-', 1), '_', 1)) AS project_base,
            parse_fuzzy_date(raw_pq_text) AS update_rfm_regex
        FROM cleaned_rfm
    ),
    rfm_norm AS (
        SELECT 
            cast("Requisition Number" AS VARCHAR) AS req_number,
            try_cast(regexp_replace(cast("Updated Requisition Approved Date" AS VARCHAR), ' .*', '') AS DATE) AS updated_date,
            "Background Update" AS background_update
        FROM df_norm
    ),
    rfm_joined AS (
        SELECT 
            r.*,
            n.updated_date AS manual_update_date,
            n.background_update,
            -- NEW PRIORITY: Take the LATEST (MAX) of manual vs regex, else fallback
            COALESCE(
                greatest(n.updated_date, r.update_rfm_regex),
                n.updated_date, 
                r.update_rfm_regex,
                try_cast(r.Requisition_Approved_Date AS DATE),
                DATE '2020-01-01'
            ) AS Used_RFM_Approved_Date
        FROM rfm_with_base r
        LEFT JOIN rfm_norm n ON cast(r.Requisition_Number AS VARCHAR) = n.req_number
    )
    SELECT 
        * EXCLUDE (clean_project, project_base, raw_pq_text),
        
        -- 1. Divisi Extraction
        CASE 
            WHEN contains(Project, '-') THEN 
                CASE 
                    WHEN upper(trim(split_part(split_part(Project, '-', 2), '_', 1))) LIKE '%HRGA%' THEN 'HRGA'
                    ELSE trim(split_part(split_part(Project, '-', 2), '_', 1))
                END
            ELSE NULL
        END AS divisi,

        -- 2. Procurement LOC Mapping
        get_procurement_loc(Procurement_Name) AS procurement_loc,

        -- 3. Advanced PT Extraction
        extract_pt_name(project_base, clean_project) AS pt,

        -- 4. Location Grouping
        get_location_group(Project) AS location_group,

        -- 5. Aging Dates
        date_diff('day', try_cast(Requisition_Approved_Date AS DATE), current_date) AS aging_req_approved,
        date_diff('day', try_cast(Used_RFM_Approved_Date AS DATE), current_date) AS aging_used_req_approved

    FROM rfm_joined
    """

    print("Running DuckDB Silver transformations for RFM...")
    silver_df = con.query(query).df()
    con.close()

    return silver_df

if __name__ == "__main__":
    rfm_file = os.path.join("daily", "downloads", "Requisition Entry List.xlsx")
    result = transform_rfm_silver(rfm_file)
    if result is not None:
        print("\nPreview of RFM Silver Data (First 5 rows):")
        cols = ['Project', 'Procurement_Name', 'divisi', 'procurement_loc', 'pt']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
