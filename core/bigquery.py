import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

def load_dataframe_to_bq(bq_client, df, table, dataset):
    """
    Core function to load a dataframe to BigQuery with auto-dataset creation and logging.
    """
    # Check if dataset exists, if not create it
    dataset_id = f"{bq_client.project}.{dataset}"
    try:
        bq_client.get_dataset(dataset_id)
    except NotFound:
        print(f"Dataset {dataset_id} not found. Creating it...")
        new_dataset = bigquery.Dataset(dataset_id)
        new_dataset.location = "US" 
        bq_client.create_dataset(new_dataset, timeout=30)
        print(f"Dataset {dataset_id} created successfully.")

    # clean columns (standardize for BQ)
    df.columns = [
        col.replace(" ", "_").replace("/", "_").replace("-", "_").replace("%", "pct")
        for col in df.columns
    ]

    # config setup
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE", 
        autodetect=True, 
    )

    # load to bq
    project_id = bq_client.project 
    table_id = f"{project_id}.{dataset}.{table}"
    
    print(f"Syncing to: {table_id}...")
    job = bq_client.load_table_from_dataframe(df, table_id, job_config=job_config)
    
    job.result()  
    print(f"Successfully loaded {len(df)} rows to {table_id}")
    
    # Explicit logging with clickable link
    table_url = f"https://console.cloud.google.com/bigquery?project={project_id}&ws=1&p={project_id}&d={dataset}&t={table}&page=table"
    print(f"Table Link: {table_url}")

def upload_to_bq(bq_client, file_path, table, dataset):
    """
    Wrapper for Excel and Parquet files.
    """
    print(f"reading data from {file_path}")
    if file_path.endswith('.parquet'):
        df = pd.read_parquet(file_path)
    else:
        df = pd.read_excel(file_path)
    load_dataframe_to_bq(bq_client, df, table, dataset)