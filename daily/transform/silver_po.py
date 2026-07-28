import duckdb
import os
import pandas as pd
from datetime import datetime
from core.transform_utils import register_silver_macros, init_duckdb_view

def transform_po_silver(raw_path, tl_path, rfm_df=None):
    """
    Transforms PO data and merges with TL data using DuckDB.
    Supports both .xlsx and .parquet inputs.
    """
    # Initialize DuckDB
    con = duckdb.connect()

    # 1. Load PO data
    print(f"Reading PO data from {raw_path}...")
    if not init_duckdb_view(con, raw_path, 'df_po'):
        con.close()
        return None

    # Register macros
    register_silver_macros(con)

    # 2. Load TL data
    has_tl = False
    if tl_path and os.path.exists(tl_path):
        print(f"Reading TL data from {tl_path}...")
        has_tl = True
        init_duckdb_view(con, tl_path, 'df_tl')
    else:
        print("Warning: TL file not found. Using empty mapping.")
        df_tl_empty = pd.DataFrame(columns=['Transfer_Number', 'PIC', 'Shipping_Co'])
        con.register('df_tl', df_tl_empty)

    # 3. Load RFM data (from pre-processed dataframe)
    if rfm_df is not None:
        con.register('df_rfm', rfm_df)
    else:
        df_rfm_empty = pd.DataFrame(columns=['Requisition_Number', 'Used_RFM_Approved_Date', 'manual_update_date', 'update_rfm_regex', 'background_update'])
        con.register('df_rfm', df_rfm_empty)

    # 3. RUN TRANSFORMATION
    # We use string_agg for CONCATENATEX behavior
    # We use LIKE join for CONTAINSSTRING behavior
    
    query = r"""
    WITH tl_agg AS (
        -- Pre-aggregate TL data if multiple TLs exist for one number (unlikely but safe)
        SELECT 
            Transfer_Number,
            string_agg(DISTINCT PIC, ', ') AS all_pic,
            string_agg(DISTINCT Shipping_Co, ', ') AS shipped_by
        FROM df_tl
        GROUP BY Transfer_Number
    ),
    cleaned_po AS (
        SELECT 
            po.*,
            clean_dept_or_project(Department) AS clean_dept,
            translate_indo_months(Req_Progress_Status) AS raw_pq_text
        FROM df_po po
    ),
    po_with_base AS (
        -- Extract the base parts before '-' or '_'
        SELECT 
            *,
            trim(split_part(split_part(clean_dept, '-', 1), '_', 1)) AS dept_base,
            parse_fuzzy_date(raw_pq_text) AS po_update_regex
        FROM cleaned_po
    ),
    po_joined AS (
        SELECT 
            c.*,
            -- DAX CONCATENATEX equivalent
            (SELECT string_agg(t.all_pic, ', ') FROM tl_agg t WHERE contains(c.TL_Number, t.Transfer_Number)) AS all_pic,
            (SELECT string_agg(t.shipped_by, ', ') FROM tl_agg t WHERE contains(c.TL_Number, t.Transfer_Number)) AS shipped_by,
            n.manual_update_date,
            -- Priority: PO's own status > RFM status join
            COALESCE(c.po_update_regex, n.update_rfm_regex) AS update_rfm_regex,
            -- Final Unified Priority
            COALESCE(
                n.manual_update_date, 
                c.po_update_regex,
                n.update_rfm_regex,
                try_cast(c.Requisition_Approved_Date AS DATE),
                DATE '2020-01-01'
            ) AS Used_RFM_Approved_Date,
            n.background_update
        FROM po_with_base c
        LEFT JOIN df_rfm n ON cast(c.Requisition_Number AS VARCHAR) = cast(n.Requisition_Number AS VARCHAR)
    )
    SELECT 
        * EXCLUDE (clean_dept, dept_base, background_update),
        background_update, 
        -- 1. Aging calculations
        date_diff('day', try_cast(Receive_PO_Date AS DATE), current_date) AS aging_receive,
        date_diff('day', try_cast(Shipped_Date AS DATE), current_date) AS aging_ship,
        date_diff('day', try_cast(Created_TL_Date AS DATE), current_date) AS aging_tl,
        date_diff('day', try_cast(PO_Approval_Date AS DATE), current_date) AS aging_po_approve,
        date_diff('day', try_cast(PO_Submit_Date AS DATE), current_date) AS aging_po_submit,
        date_diff('day', try_cast(Used_RFM_Approved_Date AS DATE), current_date) AS aging_used_req_approved,
        
        -- 2. Advanced PT Extraction
        extract_pt_name(dept_base, clean_dept) AS pt,

        -- 3. Divisi Extraction
        CASE 
            WHEN contains(Department, '-') AND contains(Department, '_') THEN 
                    trim(split_part(split_part(Department, '-', 2), '_', 1))
                ELSE NULL
        END AS divisi,

        -- 4. Fulfillment Flags
        CASE 
            WHEN Qty_Order = Qty_Received AND Qty_Order = Qty_Shipped AND Qty_Order = TL_Qty_Received THEN 1
            ELSE 0
        END AS fullfilled_po,

        CASE 
            WHEN Qty_Received = Qty_Shipped AND Qty_Received = TL_Qty_Received THEN 1
            ELSE 0
        END AS fullfilled_logistic,

        CASE 
            WHEN Qty_Order = Qty_Received AND Qty_Order = Qty_Shipped AND Qty_Order = TL_Qty_Received AND Qty_Order = Qty_Handover THEN 1
            ELSE 0
        END AS fullfilled_handover,

        -- 5. Location Grouping
        get_location_group(Department) AS location_group,

        -- 6. Procurement LOC Mapping
        get_procurement_loc(Procurement_Name) AS procurement_loc,

        -- 7. Boolean Status Flags
        (Qty_Handover = Qty_Received) AS is_handover,
        (Qty_Order = Qty_Received) AS is_po_fully_receive,
        (PO_Receive_Location = Final_Destination_Location) AS is_transit
        
    FROM po_joined
    """

    print("Running DuckDB Silver transformations and merging...")
    silver_df = con.query(query).df()
    con.close()

    return silver_df

if __name__ == "__main__":
    # For local testing
    po_file = os.path.join("daily", "downloads", "PO Entry List.xlsx")
    tl_file = os.path.join("daily", "downloads", "Transfer List.xlsx")
    
    result = transform_po_silver(po_file, tl_file)
    if result is not None:
        print("\nPreview of Silver Data (First 5 rows):")
        cols = ['PO_Number', 'TL_Number', 'all_pic', 'shipped_by', 'is_handover', 'pt', 'aging_used_req_approved']
        # Show existing columns
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
