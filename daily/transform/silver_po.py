import duckdb
import os
import pandas as pd
from datetime import datetime

def transform_po_silver(raw_path, tl_path):
    """
    Transforms PO data and merges with TL data using DuckDB.
    Supports both .xlsx and .parquet inputs.
    """
    if not os.path.exists(raw_path):
        print(f"Error: PO file {raw_path} not found.")
        return None

    # Initialize DuckDB
    con = duckdb.connect()

    # 1. Load PO data
    print(f"Reading PO data from {raw_path}...")
    if raw_path.endswith('.parquet'):
        df_po = pd.read_parquet(raw_path)
    else:
        df_po = pd.read_excel(raw_path)
    
    # Standardize column names
    df_po.columns = [
        c.replace(' ', '_').replace('/', '_').replace('-', '_').replace('%', 'pct') 
        for c in df_po.columns
    ]

    # 2. Load TL data
    df_tl = None
    if tl_path and os.path.exists(tl_path):
        print(f"Reading TL data from {tl_path}...")
        if tl_path.endswith('.parquet'):
            df_tl = pd.read_parquet(tl_path)
        else:
            df_tl = pd.read_excel(tl_path)
        
        df_tl.columns = [
            c.replace(' ', '_').replace('/', '_').replace('-', '_') 
            for c in df_tl.columns
        ]
    else:
        print("Warning: TL file not found. Skipping TL merge.")

    # 3. RUN TRANSFORMATION
    # We use string_agg for CONCATENATEX behavior
    # We use LIKE join for CONTAINSSTRING behavior
    
    query = """
    WITH tl_agg AS (
        -- Pre-aggregate TL data if multiple TLs exist for one number (unlikely but safe)
        SELECT 
            Transfer_Number,
            string_agg(DISTINCT PIC, ', ') AS all_pic,
            string_agg(DISTINCT Shipping_Co, ', ') AS shipped_by
        FROM df_tl
        GROUP BY Transfer_Number
    ),
    po_with_tl AS (
        SELECT 
            po.*,
            -- DAX CONCATENATEX equivalent
            (SELECT string_agg(t.all_pic, ', ') FROM tl_agg t WHERE po.TL_Number LIKE '%' || t.Transfer_Number || '%') AS all_pic,
            (SELECT string_agg(t.shipped_by, ', ') FROM tl_agg t WHERE po.TL_Number LIKE '%' || t.Transfer_Number || '%') AS shipped_by
        FROM df_po po
    )
    SELECT 
        *,
        -- 1. Aging calculations
        (current_date - try_cast(Receive_PO_Date AS DATE)) AS aging_receive,
        (current_date - try_cast(Shipped_Date AS DATE)) AS aging_ship,
        (current_date - try_cast(Created_TL_Date AS DATE)) AS aging_tl,
        (current_date - try_cast(PO_Approval_Date AS DATE)) AS aging_po_approve,
        
        -- 2. PT Extraction
        CASE 
            WHEN contains(Department, '-') THEN trim(split_part(Department, '-', 1))
            ELSE NULL 
        END AS pt,

        -- 3. Boolean Status Flags
        (Qty_Handover = Qty_Received) AS is_handover,
        (Qty_Order = Qty_Received) AS is_po_fully_receive,
        (PO_Receive_Location = Final_Destination_Location) AS is_transit
        
    FROM po_with_tl
    """ if df_tl is not None else """
    SELECT 
        *,
        (current_date - try_cast(Receive_PO_Date AS DATE)) AS aging_receive,
        (current_date - try_cast(Shipped_Date AS DATE)) AS aging_ship,
        (current_date - try_cast(Created_TL_Date AS DATE)) AS aging_tl,
        (current_date - try_cast(PO_Approval_Date AS DATE)) AS aging_po_approve,
        CASE WHEN contains(Department, '-') THEN trim(split_part(Department, '-', 1)) ELSE NULL END AS pt,
        (Qty_Handover = Qty_Received) AS is_handover,
        (Qty_Order = Qty_Received) AS is_po_fully_receive,
        (PO_Receive_Location = Final_Destination_Location) AS is_transit
    FROM df_po
    """

    print("Running DuckDB Silver transformations and merging...")
    silver_df = con.query(query).df()

    return silver_df

if __name__ == "__main__":
    # For local testing
    po_file = os.path.join("daily", "downloads", "PO Entry List.xlsx")
    tl_file = os.path.join("daily", "downloads", "Transfer List.xlsx")
    
    result = transform_po_silver(po_file, tl_file)
    if result is not None:
        print("\nPreview of Silver Data (First 5 rows):")
        cols = ['PO_Number', 'TL_Number', 'all_pic', 'shipped_by', 'is_handover', 'pt']
        # Show existing columns
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
