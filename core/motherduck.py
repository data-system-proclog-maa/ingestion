import os
import pandas as pd
import duckdb

def load_dataframe_to_motherduck(con, df, table_name):
    """
    Core function to load a dataframe to MotherDuck.
    Equivalent to load_dataframe_to_bq and load_dataframe_to_postgres.
    """
    # clean columns (standardize for motherduck - lowercase_snake_case)
    clean_cols = {
        col: col.replace(" ", "_").replace("/", "_").replace("-", "_").replace("%", "pct").lower()
        for col in df.columns
    }
    df = df.rename(columns=clean_cols)

    print(f"Syncing to MotherDuck table: {table_name}...")
    try:
        # DuckDB can register and query pandas DataFrames directly in SQL
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
        print(f"Successfully loaded {len(df)} rows to MotherDuck table {table_name}")
    except Exception as e:
        print(f"Failed to load data to MotherDuck: {e}")
        raise e

def upload_to_motherduck(con, file_path, table_name):
    """
    Wrapper for Excel and Parquet files.
    """
    print(f"reading data from {file_path}")
    if file_path.endswith('.parquet'):
        df = pd.read_parquet(file_path)
    else:
        df = pd.read_excel(file_path)
    load_dataframe_to_motherduck(con, df, table_name)

def upload_df_to_motherduck(df, table_name):
    """
    Directly uploads a pandas DataFrame to MotherDuck by opening its own connection.
    Does not require passing an active connection object.
    """
    token = os.getenv("MD_TOKEN")
    if not token:
        raise ValueError("MD_TOKEN is not found in .env")
        
    con = duckdb.connect(f"md:?motherduck_token={token}")
    try:
        load_dataframe_to_motherduck(con, df, table_name)
    finally:
        con.close()