import pandas as pd

def extract_table(engine, table):
    query = f"""
    SELECT *
    FROM {table}
    """
    return pd.read_sql(query, engine)