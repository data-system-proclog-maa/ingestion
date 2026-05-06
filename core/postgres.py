import pandas as pd
from sqlalchemy import create_engine

def load_dataframe_to_postgres(engine, df, table_name, schema="public", if_exists="replace"):
    """
    Core function to load a dataframe to PostgreSQL.
    Equivalent to load_dataframe_to_bq but for Postgres.
    """
    # clean columns (standardize for postgres - no spaces, etc)
    df.columns = [
        col.replace(" ", "_").replace("/", "_").replace("-", "_").replace("%", "pct").lower()
        for col in df.columns
    ]

    print(f"Syncing to PostgreSQL table: {schema}.{table_name}...")
    try:
        df.to_sql(
            name=table_name,
            con=engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
            method='multi'  # faster inserts
        )
        print(f"Successfully loaded {len(df)} rows to {schema}.{table_name}")
    except Exception as e:
        print(f"Failed to load data to PostgreSQL: {e}")
        raise e

def upload_to_postgres(engine, file_path, table_name, schema="public", if_exists="replace"):
    """
    Wrapper for Excel and Parquet files.
    """
    print(f"reading data from {file_path}")
    if file_path.endswith('.parquet'):
        df = pd.read_parquet(file_path)
    else:
        df = pd.read_excel(file_path)
    load_dataframe_to_postgres(engine, df, table_name, schema, if_exists)
