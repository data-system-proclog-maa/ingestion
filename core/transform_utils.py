import os
import pandas as pd
import duckdb

def register_silver_macros(con: duckdb.DuckDBPyConnection):
    """
    Registers reusable SQL macros on the given DuckDB connection.
    """
    # 1. Clean department/project string (remove leading X and whitespace)
    con.execute(r"""
    CREATE OR REPLACE MACRO clean_dept_or_project(val) AS 
        trim(CASE 
            WHEN upper(trim(val)) LIKE 'X%' THEN substr(trim(upper(val)), 2) 
            ELSE upper(trim(val)) 
        END);
    """)

    # 2. Translate Indonesian month names to English standard abbreviations and extract status text
    con.execute(r"""
    CREATE OR REPLACE MACRO translate_indo_months(val) AS 
        regexp_extract(
            replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
                val, 
                'Sept', 'Sep'), 'Mei', 'May'), 'Agu', 'Aug'), 'Okt', 'Oct'), 'Des', 'Dec'), 
                'Peb', 'Feb'), 'Agst', 'Aug'), 'Agustus', 'Aug'), 'Desember', 'Dec'), 'Januari', 'Jan'), 
                'Pebruari', 'Feb'), 'Maret', 'Mar'), 'Juni', 'Jun'), 'Juli', 'Jul'), 'Oktober', 'Oct'), 'Nopember', 'Nov'),
            '(?i)finalisasi\s+([^\r\n]+)', 1
        );
    """)

    # 3. Parse date string with fallback formats
    con.execute(r"""
    CREATE OR REPLACE MACRO parse_fuzzy_date(raw_text) AS 
        COALESCE(
            try_cast(regexp_extract(raw_text, '([0-9]{4}-[0-9]{1,2}-[0-9]{1,2})', 1) AS DATE),
            strptime(nullif(regexp_extract(raw_text, '([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})', 1), ''), '%d/%m/%Y')::DATE,
            try_cast(regexp_extract(raw_text, '([0-9]{1,2}-[0-9]{1,2}-[0-9]{4})', 1) AS DATE),
            strptime(nullif(regexp_extract(raw_text, '([0-9]{1,2}\s+[a-zA-Z]{3}\s+[0-9]{4})', 1), ''), '%d %b %Y')::DATE,
            strptime(nullif(regexp_extract(raw_text, '([0-9]{1,2}\s+[a-zA-Z]{4,}\s+[0-9]{4})', 1), ''), '%d %B %Y')::DATE
        );
    """)

    # 4. Advanced PT Extraction
    con.execute(r"""
    CREATE OR REPLACE MACRO extract_pt_name(dept_base, clean_dept) AS 
        CASE 
            WHEN dept_base = 'IMS' THEN
                CASE 
                    WHEN clean_dept LIKE '%147%' THEN 'IMS 147'
                    WHEN clean_dept LIKE '%52%' THEN 'IMS 52'
                    ELSE 'IMS'
                END
            WHEN dept_base = 'MPS' THEN
                CASE WHEN clean_dept LIKE '%SC%' THEN 'MPS SC' ELSE 'MPS' END
            WHEN dept_base = 'MMP' THEN
                CASE 
                    WHEN contains(clean_dept, '-') THEN
                        CASE 
                            WHEN trim(split_part(clean_dept, '-', -1)) = 'KDI' THEN 'MMP LAR'
                            ELSE 'MMP ' || trim(split_part(clean_dept, '-', -1))
                        END
                    ELSE 'MMP'
                END
            ELSE dept_base 
        END;
    """)

    # 5. Location Grouping
    con.execute(r"""
    CREATE OR REPLACE MACRO get_location_group(dept) AS 
        CASE 
            WHEN upper(trim(split_part(dept, '-', -1))) = 'HO' THEN 'HO'
            WHEN upper(trim(split_part(dept, '-', -1))) IN ('PALU', 'LAR', 'LWK', 'KDI', 'POM', 'KNW', 'WATU', 'LAEYA', 'MUNA') THEN 'Sulawesi'
            WHEN upper(trim(split_part(dept, '-', -1))) IN ('OBI', 'FLUK', 'BARU', 'TTE', 'LWI') THEN 'Halmahera'
            ELSE 'Other'
        END;
    """)

    # 6. Procurement LOC Mapping
    con.execute(r"""
    CREATE OR REPLACE MACRO get_procurement_loc(buyer_name) AS 
        CASE
            WHEN buyer_name IN (
                'Johnson', 'Sandi Dwi Putra', 'Puji Astuti', 'Yohana Ratih Amalia', 
                'Syifa Ramadhani Luthfi', 'Rizal Agus Fianto', 'Linda Permata Sari', 
                'Auriel', 'Rifqy', 'Stheven Immanuel', 'Ferdinand', 'George', 'Admin', 
                'Zana Chobita', 'Syifa Alifia', 'Fajar Amry', 'Nathanael', 
                'Laurensius Adi', 'Axel', 'Melia Sari', 'Laurentius Adi',
                'Satria Ajidarma', 'Team Kontrak', 'Jose Miguel'
            ) THEN 'PIC HO'
            WHEN buyer_name IN ('Fairus Mubakri', 'Irwan', 'Ady', 'Muhammad Hamka') THEN 'PIC LAR'
            WHEN buyer_name IN ('Rona Justhafist', 'Joko', 'Victo', 'Rakan', 'Aldi') THEN 'PIC OBI'
            WHEN buyer_name IN ('Olvan') THEN 'PIC PALU'
            WHEN contains(buyer_name, '/') THEN 'Mixed PIC'
            ELSE 'Empty'
        END;
    """)

    # 7. Lebaran Overlap Macro
    con.execute(r"""
    CREATE OR REPLACE MACRO lebaran_overlap(s, e, l_s, l_e) AS 
        CASE 
            WHEN GREATEST(s + INTERVAL 1 DAY, l_s) <= LEAST(e, l_e) 
            THEN datediff('day', GREATEST(s + INTERVAL 1 DAY, l_s), LEAST(e, l_e)) + 1 
            ELSE 0 
        END;
    """)

    # 8. Days Excluding Lebaran Macro
    con.execute(r"""
    CREATE OR REPLACE MACRO diff_excl_lebaran(start_d, end_d) AS 
        CASE 
            WHEN start_d IS NULL OR end_d IS NULL THEN NULL 
            WHEN start_d = end_d THEN 0 
            WHEN start_d < end_d THEN 
                datediff('day', start_d, end_d) 
                - lebaran_overlap(start_d, end_d, DATE '2025-03-28', DATE '2025-04-13') 
                - lebaran_overlap(start_d, end_d, DATE '2026-03-18', DATE '2026-03-31') 
            ELSE 
                -(
                    datediff('day', end_d, start_d) 
                    - lebaran_overlap(end_d, start_d, DATE '2025-03-28', DATE '2025-04-13') 
                    - lebaran_overlap(end_d, start_d, DATE '2026-03-18', DATE '2026-03-31') 
                ) 
        END;
    """)

    # 9. Category Merged Macro
    con.execute(r"""
    CREATE OR REPLACE MACRO merge_item_category(item_cat, unit_val) AS 
        CASE 
            WHEN upper(trim(coalesce(item_cat, ''))) LIKE '%XCMG%' THEN 'Spare Part XCMG' 
            WHEN upper(trim(coalesce(item_cat, ''))) LIKE '%SANY%' THEN 'Spare Part SANY' 
            WHEN upper(trim(coalesce(item_cat, ''))) LIKE '%ZS%' THEN 'Spare Part ZS' 
            WHEN upper(trim(coalesce(item_cat, ''))) LIKE '%TIRE DT%' THEN 
                CASE WHEN upper(trim(coalesce(unit_val, ''))) LIKE '%SET%' THEN 'Tire DT - Set' ELSE 'Tire DT - non Set' END 
            ELSE item_cat 
        END;
    """)


def init_duckdb_view(con: duckdb.DuckDBPyConnection, file_path: str, view_name: str) -> bool:
    """
    Checks if raw_path exists, converts backslashes, and registers a DuckDB view.
    Supports both .parquet and .xlsx files (falling back to pandas if .xlsx).
    Returns True if successfully registered, False otherwise.
    """
    if not file_path or not os.path.exists(file_path):
        print(f"Error: Target file {file_path} not found.")
        return False

    base, ext = os.path.splitext(file_path)
    parquet_counterpart = base + ".parquet"
    
    if ext.lower() in ['.xlsx', '.xls']:
        if os.path.exists(parquet_counterpart):
            safe_path = parquet_counterpart.replace('\\', '/')
            con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{safe_path}')")
        else:
            try:
                df = pd.read_excel(file_path)
                df.columns = [str(c).replace(' ', '_').replace('/', '_').replace('-', '_').replace('%', 'pct') for c in df.columns]
                con.register(view_name, df)
            except Exception as e:
                print(f"Error reading Excel file {file_path}: {e}")
                return False
    else:
        safe_path = file_path.replace('\\', '/')
        con.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{safe_path}')")

    # Validate registered schema
    cols = [col[0] for col in con.execute(f"DESCRIBE {view_name}").fetchall()]
    if len(cols) <= 2 and any(c.lower().startswith('field') for c in cols):
        print(f"Error: {view_name} has invalid dummy/empty schema {cols}.")
        return False

    return True


def fetch_normalization_df(con: duckdb.DuckDBPyConnection, url: str, view_name: str, fallback_columns: list):
    """
    Fetches normalization CSV from Google Sheets URL and registers it in DuckDB.
    Falls back to an empty DataFrame on failure.
    """
    try:
        df_norm = pd.read_csv(url)
        con.register(view_name, df_norm)
    except Exception as e:
        print(f"Warning: Failed to fetch normalization table for {view_name}. {e}")
        df_norm = pd.DataFrame(columns=fallback_columns)
        con.register(view_name, df_norm)
    return df_norm
