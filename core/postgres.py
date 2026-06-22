import pandas as pd
from sqlalchemy import create_engine
import csv
from io import StringIO

def psql_insert_copy(table, conn, keys, data_iter):
    """
    Executes SQL statement inserting data using Postgres COPY for massive performance gains.
    """
    dbapi_conn = conn.connection
    if hasattr(dbapi_conn, "dbapi_connection"):
        dbapi_conn = dbapi_conn.dbapi_connection
        
    with dbapi_conn.cursor() as cur:
        s_buf = StringIO()
        writer = csv.writer(s_buf)
        writer.writerows(data_iter)
        s_buf.seek(0)

        columns = ', '.join('"{}"'.format(k) for k in keys)
        if table.schema:
            table_name = '{}.{}'.format(table.schema, table.name)
        else:
            table_name = '"{}"'.format(table.name)

        sql = 'COPY {} ({}) FROM STDIN WITH CSV'.format(table_name, columns)
        cur.copy_expert(sql=sql, file=s_buf)

def load_dataframe_to_postgres(engine, df, table_name, schema="public", if_exists="replace"):
    """
    Core function to load a dataframe to PostgreSQL.
    Equivalent to load_dataframe_to_bq but for Postgres.
    """
    # clean columns (standardize for postgres - no spaces, etc)
    clean_cols = {
        col: col.replace(" ", "_").replace("/", "_").replace("-", "_").replace("%", "pct").lower()
        for col in df.columns
    }
    df = df.rename(columns=clean_cols)

    print(f"Syncing to PostgreSQL table: {schema}.{table_name}...")
    try:
        df.to_sql(
            name=table_name,
            con=engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
            method=psql_insert_copy  # Use fast bulk COPY method
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
