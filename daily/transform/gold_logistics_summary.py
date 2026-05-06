import duckdb
import pandas as pd

def transform_gold_logistics(po_processed_df):
    """
    Transforms the Master Processed PO data into a daily Logistics Summary.
    Recreates the Power Query UNION of PO receiving and TL receiving.
    """
    if po_processed_df is None or po_processed_df.empty:
        return None

    # Initialize DuckDB
    con = duckdb.connect()
    
    # We pass the pandas dataframe into duckdb just by referencing its variable name 'df'
    df = po_processed_df

    query = """
    WITH filtered_base AS (
        -- 1. Common Filter: Exclude categories
        SELECT * 
        FROM df
        WHERE item_category IS NULL 
           OR (
               item_category NOT ILIKE '%solar%' AND 
               item_category NOT ILIKE '%jasa%' AND 
               item_category NOT ILIKE '%kontrak%'
           )
    ),
    po_summary AS (
        -- 2. Build the PO Summary Table (Daily)
        SELECT 
            CAST(receive_po_date AS DATE) AS "Date",
            po_receive_location AS "Location",
            SUM(try_cast(qty_received AS DOUBLE)) AS "Item_Qty",
            COUNT(*) AS "Item_Count",
            COUNT(DISTINCT po_number) AS "PO_Number",
            'PO' AS "Source"
        FROM filtered_base
        WHERE qty_received IS NOT NULL AND receive_po_date IS NOT NULL
        GROUP BY CAST(receive_po_date AS DATE), po_receive_location
    ),
    tl_summary AS (
        -- 3. Build the TL Summary Table (Daily)
        SELECT 
            CAST(received_tl_date AS DATE) AS "Date",
            final_destination_location AS "Location",
            SUM(try_cast(tl_qty_received AS DOUBLE)) AS "Item_Qty",
            COUNT(*) AS "Item_Count",
            COUNT(DISTINCT po_number) AS "PO_Number",
            'TL' AS "Source"
        FROM filtered_base
        WHERE tl_qty_received IS NOT NULL AND received_tl_date IS NOT NULL
        GROUP BY CAST(received_tl_date AS DATE), final_destination_location
    )
    -- 4. Combine (UNION) Both Tables
    SELECT * FROM po_summary
    UNION ALL
    SELECT * FROM tl_summary
    ORDER BY "Date" DESC
    """
    
    print("Running Gold Logistics Summary transformation...")
    gold_df = con.query(query).df()
    
    return gold_df
