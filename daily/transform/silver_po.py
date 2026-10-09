import duckdb
import os
import pandas as pd
from datetime import datetime
from core.config import dailyConfig
from core.transform_utils import register_silver_macros, init_duckdb_view, fetch_normalization_df

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

    # 4. Fetch Normalization Sheets for Lead Time & On-Time Performance
    print("Fetching TimeDate Normalisasi from Google Sheets...")
    fetch_normalization_df(con, dailyConfig.URL_TIMEDATE_NORMALISASI, 'df_timedate_raw', ['PO Number', 'timedate'])
    con.execute("""
    CREATE OR REPLACE VIEW df_timedate_norm AS 
    SELECT cast("PO Number" AS VARCHAR) AS po_number_norm, try_cast("timedate" AS INTEGER) AS timedate_days 
    FROM df_timedate_raw;
    """)

    print("Fetching Non-workdays (Holidays) from Google Sheets...")
    fetch_normalization_df(con, dailyConfig.URL_HOLIDAYS, 'df_holidays_raw', ['NONWORKDAYS'])
    con.execute("""
    CREATE OR REPLACE VIEW df_holidays AS 
    SELECT try_cast(strptime(nullif(trim(NONWORKDAYS), ''), '%d/%m/%Y') AS DATE) AS holiday_date 
    FROM df_holidays_raw 
    WHERE NONWORKDAYS IS NOT NULL;
    """)

    # 5. RUN TRANSFORMATION
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
            row_number() OVER () AS orig_row_id,
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
    ),
    po_markers AS (
        SELECT 
            p.*,
            t.timedate_days,
            upper(trim(split_part(Department, '-', -1))) AS site_suffix,
            contains(Department, '__') AS is_ho_type,
            CASE WHEN trim(Item_Category) IN (
                'Consumable Workshop', 'Packaging', 'Alat dan Bahan Bangunan', 
                'Bolt dan Nut', 'Elektrikal', 'Consumable Cleaning', 
                'Perabotan', 'Peralatan Geologi', 'Peralatan Dapur'
            ) THEN 1 ELSE 0 END AS is_special_lc,
            CASE 
                WHEN lower(trim(coalesce(Item_Category, ''))) IN (
                    'kontrak', 'seragam', 'jasa logistik', 'jasa/service', 'atk', 'cetak', 
                    'makanan dan minuman', 'seragam security', 'x kebutuhan kantin', 
                    'x kebutuhan mess', 'x medical dan obat', 'petty cash', 'test'
                )
                OR lower(coalesce(Department, '')) LIKE '%test%'
                OR trim(coalesce(Requisition_Type, '')) = 'Consignment'
                OR (lower(trim(coalesce(Item_Category, ''))) = 'apd' AND lower(coalesce(Item_Name, '')) LIKE '%sepatu%')
                THEN 1 ELSE 0
            END AS cat_marker,
            CASE 
                WHEN trim(coalesce(Requisition_Type, '')) != 'Consignment'
                AND coalesce(Item_Category, '') LIKE '%XCMG%'
                AND (
                    coalesce(Background_Needs, '') LIKE '%Pengambilan%'
                    OR coalesce(Background_Needs, '') LIKE '%Berita acara pengeluaran%'
                    OR coalesce(Background_Needs, '') LIKE '%BA%'
                    OR coalesce(Background_Needs, '') LIKE '%Consignment%'
                )
                THEN 1 ELSE 0
            END AS cat_xcmg_marker
        FROM po_joined p
        LEFT JOIN df_timedate_norm t ON p.PO_Number = t.po_number_norm
    ),
    po_grouped AS (
        SELECT 
            *,
            max(cat_marker) OVER (PARTITION BY PO_Number) AS max_cat_marker,
            max(cat_xcmg_marker) OVER (PARTITION BY PO_Number) AS max_xcmg_marker,
            row_number() OVER (PARTITION BY PO_Number ORDER BY orig_row_id) AS po_row_num,
            CASE 
                WHEN lower(trim(coalesce(Item_Category, ''))) = 'petty cash' OR upper(coalesce(Department, '')) LIKE '%TEST%' THEN 0
                WHEN site_suffix IN ('OBI', 'FLUK', 'BARU', 'LWI') THEN
                    CASE WHEN is_ho_type OR is_special_lc = 1 THEN 43 ELSE 15 END
                WHEN site_suffix IN ('LAR', 'LWK', 'PALU', 'KDI', 'MUNA', 'TKE', 'WATU', 'LAEYA') THEN
                    CASE WHEN is_ho_type OR is_special_lc = 1 THEN 36 ELSE 15 END
                WHEN site_suffix = 'HO' OR is_ho_type OR contains(Department, '-') THEN 15
                ELSE 0
            END AS default_sla_days
        FROM po_markers
    ),
    po_valued AS (
        SELECT 
            *,
            CASE WHEN max_cat_marker = 1 OR max_xcmg_marker = 1 THEN 0 ELSE 1 END AS raw_val
        FROM po_grouped
    ),
    po_summed AS (
        SELECT 
            *,
            sum(raw_val) OVER (PARTITION BY PO_Number) AS sum_raw_val
        FROM po_valued
    ),
    po_calc_prep AS (
        SELECT 
            *,
            CASE 
                WHEN lower(trim(coalesce(Item_Category, ''))) = 'petty cash' THEN 0
                WHEN upper(coalesce(Department, '')) LIKE '%TEST%' OR lower(trim(coalesce(Item_Category, ''))) = 'test' THEN 0
                WHEN po_row_num = 1 AND sum_raw_val = 0 THEN 1
                ELSE raw_val
            END AS is_val,
            coalesce(timedate_days, default_sla_days) AS final_sla_days,
            NULLIF(try_cast(Used_RFM_Approved_Date AS DATE), DATE '2020-01-01') AS d_used_rfm_approved,
            try_cast(PO_Submit_Date AS DATE) AS d_po_submit,
            try_cast(PO_Approval_Date AS DATE) AS d_po_approval,
            try_cast(Receive_PO_Date AS DATE) AS d_receive_po,
            try_cast(Received_TL_Date AS DATE) AS d_received_tl,
            try_cast(PO_Required_Date AS DATE) AS d_po_required,
            try_cast(Requisition_Required_Date AS DATE) AS d_req_required
        FROM po_summed
    ),
    po_metric_prep AS (
        SELECT 
            *,
            (
                is_val = 1
                AND trim(coalesce(Requisition_Type, '')) != 'Consignment'
                AND coalesce(Item_Category, '') != 'Jasa Logistik'
                AND (coalesce(Item_Category, '') != 'Solar' OR date_part('year', d_po_approval) >= 2026)
            ) AS is_calculable,
            d_used_rfm_approved + INTERVAL (final_sla_days) DAY AS time_date,
            coalesce(d_receive_po, d_received_tl) AS used_receive_date
        FROM po_calc_prep
    ),
    po_farthest AS (
        SELECT 
            *,
            greatest(d_po_required, d_req_required, time_date) AS farthest_required_date
        FROM po_metric_prep
    )
    SELECT 
        * EXCLUDE (
            clean_dept, dept_base, background_update, orig_row_id, timedate_days, 
            site_suffix, is_ho_type, is_special_lc, cat_marker, cat_xcmg_marker, 
            max_cat_marker, max_xcmg_marker, po_row_num, default_sla_days, raw_val, 
            sum_raw_val, is_val, final_sla_days, d_used_rfm_approved, d_po_submit, 
            d_po_approval, d_receive_po, d_received_tl, d_po_required, d_req_required, 
            is_calculable, time_date, used_receive_date, farthest_required_date
        ),
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
        (PO_Receive_Location = Final_Destination_Location) AS is_transit,

        -- 8. Value Performance Marker & Merged Category
        is_val AS value,
        merge_item_category(Item_Category, Unit) AS categorymerged,

        -- 9. Lead Time & On-Time Performance Metrics
        CASE 
            WHEN is_calculable AND d_used_rfm_approved IS NOT NULL AND d_po_submit IS NOT NULL 
            THEN GREATEST(0, diff_excl_lebaran(d_used_rfm_approved, d_po_submit))
            ELSE NULL 
        END AS pr_po,
        
        CASE 
            WHEN is_calculable AND d_po_submit IS NOT NULL AND d_po_approval IS NOT NULL 
            THEN GREATEST(0, diff_excl_lebaran(d_po_submit, d_po_approval))
            ELSE NULL 
        END AS po_sub_po_app,
        
        CASE 
            WHEN is_calculable AND d_used_rfm_approved IS NOT NULL AND d_po_submit IS NOT NULL 
                 AND d_receive_po IS NOT NULL AND coalesce(Item_Category, '') != 'Jasa/Service' AND d_po_approval IS NOT NULL
            THEN GREATEST(0, diff_excl_lebaran(d_po_approval, d_receive_po))
            ELSE NULL 
        END AS po_r_po,
        
        CASE 
            WHEN is_calculable AND d_used_rfm_approved IS NOT NULL AND d_po_submit IS NOT NULL 
                 AND d_receive_po IS NOT NULL AND d_received_tl IS NOT NULL 
                 AND coalesce(Item_Category, '') != 'Jasa/Service' AND Location_TL_Received IS NOT NULL 
                 AND NOT (Department LIKE '%-HO' OR site_suffix = 'HO')
            THEN GREATEST(0, diff_excl_lebaran(d_receive_po, d_received_tl))
            ELSE NULL 
        END AS r_r_site,
        
        CASE 
            WHEN is_calculable AND d_used_rfm_approved IS NOT NULL AND d_po_submit IS NOT NULL THEN
                CASE 
                    WHEN d_used_rfm_approved >= d_po_submit THEN 0
                    ELSE (
                        SELECT count(*)
                        FROM (
                            SELECT unnest(generate_series(d_used_rfm_approved, d_po_submit - INTERVAL 1 DAY, INTERVAL 1 DAY)) AS d
                        ) sub
                        WHERE dayofweek(d) NOT IN (0, 6)
                          AND cast(d AS DATE) NOT IN (SELECT holiday_date FROM df_holidays)
                    )
                END
            ELSE NULL
        END AS pr_po_sub_wd,
        
        CASE 
            WHEN is_calculable AND d_po_submit IS NOT NULL AND d_po_approval IS NOT NULL THEN
                CASE 
                    WHEN d_po_submit >= d_po_approval THEN 0
                    ELSE (
                        SELECT count(*)
                        FROM (
                            SELECT unnest(generate_series(d_po_submit, d_po_approval - INTERVAL 1 DAY, INTERVAL 1 DAY)) AS d
                        ) sub
                        WHERE dayofweek(d) NOT IN (0, 6)
                          AND cast(d AS DATE) NOT IN (SELECT holiday_date FROM df_holidays)
                    )
                END
            ELSE NULL
        END AS po_sub_po_app_wd,
        
        CASE 
            WHEN Item_Category IN ('Jasa/Service', 'Solar') THEN 1
            WHEN is_val = 1 THEN
                CASE 
                    WHEN used_receive_date IS NULL OR farthest_required_date IS NULL THEN NULL
                    WHEN Requisition_Type = 'Consignment' THEN 1
                    WHEN diff_excl_lebaran(farthest_required_date, used_receive_date) >= 1 THEN 0
                    ELSE 1
                END
            ELSE NULL
        END AS ontime

    FROM po_farthest
    """

    print("Running DuckDB Silver transformations and merging...")
    silver_df = con.query(query).df()
    con.close()

    return silver_df

if __name__ == "__main__":
    # For local testing
    po_file = os.path.join("downloads", "PO Entry List.parquet")
    tl_file = os.path.join("downloads", "Transfer List.parquet")
    
    result = transform_po_silver(po_file, tl_file)
    if result is not None:
        print("\nPreview of Silver Data (First 5 rows):")
        cols = ['PO_Number', 'TL_Number', 'categorymerged', 'all_pic', 'shipped_by', 'is_handover', 'pt', 'value', 'pr_po', 'po_sub_po_app', 'po_r_po', 'r_r_site', 'pr_po_sub_wd', 'po_sub_po_app_wd', 'ontime']
        cols = [c for c in cols if c in result.columns]
        print(result[cols].head())
