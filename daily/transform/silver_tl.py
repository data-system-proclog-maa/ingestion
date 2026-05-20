import duckdb
import os
import pandas as pd
from core.config import dailyConfig

def transform_tl_silver(raw_path):
    """
    Transforms Transfer List (TL) data using DuckDB.
    Calculates lead_time and shipped_ontime markers.
    """
    if not os.path.exists(raw_path):
        print(f"Error: TL file {raw_path} not found.")
        return None

    # Initialize DuckDB
    con = duckdb.connect()

    # Load TL data
    print(f"Reading TL data from {raw_path}...")
    safe_raw_path = raw_path.replace('\\', '/')
    con.execute(f"CREATE OR REPLACE VIEW df_tl AS SELECT * FROM read_parquet('{safe_raw_path}')")

    # Fetch Normalisasi Google Sheet
    print("Fetching TL Normalisasi from Google Sheets...")
    url = dailyConfig.URL_TL_NORMALISASI
    try:
        df_tl_norm = pd.read_csv(url)
        con.register('df_tl_norm', df_tl_norm)
    except Exception as e:
        print(f"Warning: Failed to fetch TL Normalisasi. {e}")
        # Fallback to an empty dataframe to prevent crashes
        df_tl_norm = pd.DataFrame(columns=['TL Number', 'remarks'])
        con.register('df_tl_norm', df_tl_norm)

    query = r"""
    SELECT 
        t.*,
        -- Calculate lead_time: difference in days between Shipped Date and Received Date
        -- Returns NULL if either date is missing/empty
        CASE 
            WHEN t.Shipped_Date IS NULL OR t.Received_Date IS NULL 
                 OR trim(cast(t.Shipped_Date AS VARCHAR)) = '' 
                 OR trim(cast(t.Received_Date AS VARCHAR)) = '' THEN NULL
            ELSE date_diff('day', try_cast(t.Shipped_Date AS DATE), try_cast(t.Received_Date AS DATE))
        END AS lead_time,

        -- Calculate shipped_ontime marker: 1 if TL is in normalization override list,
        -- else 1 if lead_time <= 6, else 0. NULL if lead_time is NULL.
        CASE 
            WHEN n."TL Number" IS NOT NULL THEN 1
            WHEN (
                CASE 
                    WHEN t.Shipped_Date IS NULL OR t.Received_Date IS NULL 
                         OR trim(cast(t.Shipped_Date AS VARCHAR)) = '' 
                         OR trim(cast(t.Received_Date AS VARCHAR)) = '' THEN NULL
                    ELSE date_diff('day', try_cast(t.Shipped_Date AS DATE), try_cast(t.Received_Date AS DATE))
                END
            ) IS NULL THEN NULL
            WHEN (
                CASE 
                    WHEN t.Shipped_Date IS NULL OR t.Received_Date IS NULL 
                         OR trim(cast(t.Shipped_Date AS VARCHAR)) = '' 
                         OR trim(cast(t.Received_Date AS VARCHAR)) = '' THEN NULL
                    ELSE date_diff('day', try_cast(t.Shipped_Date AS DATE), try_cast(t.Received_Date AS DATE))
                END
            ) <= 6 THEN 1
            ELSE 0
        END AS shipped_ontime

    FROM df_tl t
    LEFT JOIN df_tl_norm n ON trim(cast(t.Transfer_Number AS VARCHAR)) = trim(cast(n."TL Number" AS VARCHAR))
    """

    print("Running DuckDB Silver transformations for TL...")
    silver_df = con.query(query).df()
    con.close()

    return silver_df

if __name__ == "__main__":
    tl_file = os.path.join("downloads", "Transfer List.parquet")
    if not os.path.exists(tl_file):
        tl_file = os.path.join("downloads", "Transfer List.xlsx")
    result = transform_tl_silver(tl_file)
    if result is not None:
        print("\nPreview of TL Silver Data (First 5 rows):")
        cols = ['Transfer_Number', 'Shipped_Date', 'Received_Date', 'lead_time', 'shipped_ontime']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
