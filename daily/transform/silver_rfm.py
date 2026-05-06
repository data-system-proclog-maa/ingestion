import duckdb
import os
import pandas as pd
from datetime import datetime

def transform_rfm_silver(raw_path):
    """
    Transforms RFM data using DuckDB.
    Supports both .xlsx and .parquet inputs.
    """
    if not os.path.exists(raw_path):
        print(f"Error: RFM file {raw_path} not found.")
        return None

    # Initialize DuckDB
    con = duckdb.connect()

    # Load RFM data
    print(f"Reading RFM data from {raw_path}...")
    safe_raw_path = raw_path.replace('\\', '/')
    con.execute(f"CREATE OR REPLACE VIEW df_rfm AS SELECT * FROM read_parquet('{safe_raw_path}')")

    # Fetch Normalisasi Google Sheet
    print("Fetching RFM Normalisasi from Google Sheets...")
    url = "https://docs.google.com/spreadsheets/d/1EZ7kPPvnRqvR5UN0Vi0NNLpLTNXEArzRklsVTIGb1vc/gviz/tq?tqx=out:csv&gid=0"
    try:
        df_norm = pd.read_csv(url)
        con.register('df_norm', df_norm)
    except Exception as e:
        print(f"Warning: Failed to fetch RFM Normalisasi. {e}")
        # Fallback to an empty dataframe to prevent crashes
        df_norm = pd.DataFrame(columns=['Requisition Number', 'Updated Requisition Approved Date'])
        con.register('df_norm', df_norm)

    query = """
    WITH cleaned_rfm AS (
        SELECT 
            *,
            -- Clean Project: Remove leading 'X' and whitespace
            trim(CASE 
                WHEN upper(trim(Project)) LIKE 'X%' THEN substr(trim(upper(Project)), 2) 
                ELSE upper(trim(Project)) 
            END) AS clean_project,
        FROM df_rfm
    ),
    rfm_with_base AS (
        SELECT 
            *,
            trim(split_part(split_part(clean_project, '-', 1), '_', 1)) AS project_base
        FROM cleaned_rfm
    ),
    rfm_norm AS (
        SELECT 
            "Requisition Number" AS req_number,
            -- Clean datetime to standard date format if needed
            try_cast(regexp_replace(cast("Updated Requisition Approved Date" AS VARCHAR), ' .*', '') AS DATE) AS updated_date,
            "Background Update" AS background_update
        FROM df_norm
    ),
    rfm_joined AS (
        SELECT 
            r.*,
            n.updated_date,
            n.background_update,
            COALESCE(
                n.updated_date, 
                try_cast(r.Requisition_Approved_Date AS DATE)
            ) AS Used_RFM_Approved_Date
        FROM rfm_with_base r
        LEFT JOIN rfm_norm n ON r.Requisition_Number = n.req_number
    )
    SELECT 
        * EXCLUDE (clean_project, project_base, updated_date),
        
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
        CASE
            WHEN Procurement_Name IN (
                'Johnson', 'Sandi Dwi Putra', 'Puji Astuti', 'Yohana Ratih Amalia', 
                'Syifa Ramadhani Luthfi', 'Rizal Agus Fianto', 'Linda Permata Sari', 
                'Auriel', 'Rifqy', 'Stheven Immanuel', 'Ferdinand', 'George', 'Admin', 
                'Zana Chobita', 'Syifa Alifia', 'Fajar Amry', 'Nathanael', 
                'Laurensius Adi', 'Axel', 'Melia Sari', 'Laurentius Adi'
            ) THEN 'PIC HO'
            WHEN Procurement_Name IN ('Fairus Mubakri', 'Irwan', 'Ady', 'Muhammad Hamka') THEN 'PIC LAR'
            WHEN Procurement_Name IN ('Rona Justhafist', 'Joko', 'Victo', 'Rakan', 'Aldi') THEN 'PIC OBI'
            WHEN Procurement_Name IN ('Olvan') THEN 'PIC PALU'
            WHEN contains(Procurement_Name, '/') THEN 'Mixed PIC'
            ELSE 'Empty'
        END AS procurement_loc,

        -- 3. Advanced PT Extraction
        CASE 
            WHEN project_base = 'IMS' THEN
                CASE 
                    WHEN clean_project LIKE '%147%' THEN 'IMS 147'
                    WHEN clean_project LIKE '%52%' THEN 'IMS 52'
                    ELSE 'IMS'
                END
            WHEN project_base = 'MPS' THEN
                CASE WHEN clean_project LIKE '%SC%' THEN 'MPS SC' ELSE 'MPS' END
            WHEN project_base = 'MMP' THEN
                CASE 
                    WHEN contains(clean_project, '-') THEN
                        CASE 
                            WHEN trim(split_part(clean_project, '-', -1)) = 'KDI' THEN 'MMP LAR'
                            ELSE 'MMP ' || trim(split_part(clean_project, '-', -1))
                        END
                    ELSE 'MMP'
                END
            ELSE project_base 
        END AS pt,

        -- 4. Aging Dates
        date_diff('day', try_cast(Requisition_Approved_Date AS DATE), current_date) AS aging_req_approved,
        date_diff('day', try_cast(Used_RFM_Approved_Date AS DATE), current_date) AS aging_used_req_approved

    FROM rfm_joined
    """

    print("Running DuckDB Silver transformations for RFM...")
    silver_df = con.query(query).df()

    return silver_df

if __name__ == "__main__":
    rfm_file = os.path.join("daily", "downloads", "Requisition Entry List.xlsx")
    result = transform_rfm_silver(rfm_file)
    if result is not None:
        print("\nPreview of RFM Silver Data (First 5 rows):")
        cols = ['Project', 'Procurement_Name', 'divisi', 'procurement_loc', 'pt']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
