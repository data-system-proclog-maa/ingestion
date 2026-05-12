import duckdb
import os
import pandas as pd

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

    query = r"""
    SELECT 
        *,
        -- Calculate lead_time: difference in days between Shipped Date and Received Date
        -- Returns NULL if either date is missing/empty
        CASE 
            WHEN Shipped_Date IS NULL OR Received_Date IS NULL 
                 OR trim(cast(Shipped_Date AS VARCHAR)) = '' 
                 OR trim(cast(Received_Date AS VARCHAR)) = '' THEN NULL
            ELSE date_diff('day', try_cast(Shipped_Date AS DATE), try_cast(Received_Date AS DATE))
        END AS lead_time,

        -- Calculate shipped_ontime marker: 1 if lead_time <= 6, else 0. NULL if lead_time is NULL.
        CASE 
            WHEN (
                CASE 
                    WHEN Shipped_Date IS NULL OR Received_Date IS NULL 
                         OR trim(cast(Shipped_Date AS VARCHAR)) = '' 
                         OR trim(cast(Received_Date AS VARCHAR)) = '' THEN NULL
                    ELSE date_diff('day', try_cast(Shipped_Date AS DATE), try_cast(Received_Date AS DATE))
                END
            ) IS NULL THEN NULL
            WHEN (
                CASE 
                    WHEN Shipped_Date IS NULL OR Received_Date IS NULL 
                         OR trim(cast(Shipped_Date AS VARCHAR)) = '' 
                         OR trim(cast(Received_Date AS VARCHAR)) = '' THEN NULL
                    ELSE date_diff('day', try_cast(Shipped_Date AS DATE), try_cast(Received_Date AS DATE))
                END
            ) <= 6 THEN 1
            ELSE 0
        END AS shipped_ontime

    FROM df_tl
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
