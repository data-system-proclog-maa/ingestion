def upload_to_bq(file_path, table, dataset):

    # read data and column cleaning
    print(f"reading data from {file_path}")
    df = pd.read_excel(file_path)

    # clean column
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
    job = bq_client.load_table_from_dataframe(df, table_id, job_config=job_config)
    
    job.result()  
    print(f"Successfully loaded {len(df)} rows to {table_id}")