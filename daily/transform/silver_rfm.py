import duckdb
import os
import pandas as pd
from datetime import datetime
from core.config import dailyConfig

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
    url = dailyConfig.URL_RFM_NORMALISASI
    try:
        df_norm = pd.read_csv(url)
        con.register('df_norm', df_norm)
    except Exception as e:
        print(f"Warning: Failed to fetch RFM Normalisasi. {e}")
        # Fallback to an empty dataframe to prevent crashes
        df_norm = pd.DataFrame(columns=['Requisition Number', 'Updated Requisition Approved Date'])
        con.register('df_norm', df_norm)

    query = r"""
    WITH    cleaned_rfm AS (
        SELECT 
            *,
            -- Clean Project: Remove leading 'X' and whitespace
            trim(CASE 
                WHEN upper(trim(Project)) LIKE 'X%' THEN substr(trim(upper(Project)), 2) 
                ELSE upper(trim(Project)) 
            END) AS clean_project,
            -- Extract text after "finalisasi" for date mining (UpdatedDatePQ)
            -- Translate Indonesian months to English so DuckDB can parse them
            regexp_extract(
                replace(replace(replace(replace(replace(replace(
                    replace(Progress_Status, 'Sept', 'Sep'), 
                    'Mei', 'May'), 
                    'Agu', 'Aug'), 
                    'Okt', 'Oct'), 
                    'Des', 'Dec'),
                    'Peb', 'Feb'), -- common typo
                    'Agst', 'Aug'), -- common typo
                '(?i)finalisasi\s+([^\r\n]+)', 1
            ) AS raw_pq_text
        FROM df_rfm
    ),
    rfm_with_base AS (
        SELECT 
            *,
            trim(split_part(split_part(clean_project, '-', 1), '_', 1)) AS project_base,
            -- Try to parse dates from the mined text using common patterns
            COALESCE(
                try_cast(regexp_extract(raw_pq_text, '([0-9]{4}-[0-9]{1,2}-[0-9]{1,2})', 1) AS DATE),
                try_cast(regexp_extract(raw_pq_text, '([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})', 1) AS DATE),
                try_cast(regexp_extract(raw_pq_text, '([0-9]{1,2}-[0-9]{1,2}-[0-9]{4})', 1) AS DATE),
                -- Handle "12 Sep 2024" or "12 September 2024"
                strptime(nullif(regexp_extract(raw_pq_text, '([0-9]{1,2}\s+[a-zA-Z]{3}\s+[0-9]{4})', 1), ''), '%d %b %Y'),
                strptime(nullif(regexp_extract(raw_pq_text, '([0-9]{1,2}\s+[a-zA-Z]{4,}\s+[0-9]{4})', 1), ''), '%d %B %Y')
            ) AS update_rfm_regex
        FROM cleaned_rfm
    ),
    rfm_norm AS (
        SELECT 
            "Requisition Number" AS req_number,
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
        LEFT JOIN rfm_norm n ON r.Requisition_Number = n.req_number
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

        -- 4. Location Grouping
        CASE 
            WHEN upper(trim(split_part(Project, '-', -1))) = 'HO' THEN 'HO'
            WHEN upper(trim(split_part(Project, '-', -1))) IN ('PALU', 'LAR', 'LWK', 'KDI', 'LWI', 'POM', 'KNW', 'WATU', 'LAEYA', 'MUNA') THEN 'Sulawesi'
            WHEN upper(trim(split_part(Project, '-', -1))) IN ('OBI', 'FLUK', 'BARU', 'TTE') THEN 'Halmahera'
            ELSE 'Other'
        END AS location_group,

        -- 5. Aging Dates
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
