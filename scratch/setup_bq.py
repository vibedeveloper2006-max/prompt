from google.cloud import bigquery


def setup_bigquery():
    project_id = "stadiumchecker"
    client = bigquery.Client(project=project_id)

    dataset_id = f"{project_id}.analytics"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = "US"

    try:
        dataset = client.create_dataset(dataset, timeout=30)
        print(f"Created dataset {client.project}.{dataset.dataset_id}")
    except Exception as e:
        if "Already Exists" in str(e):
            print(f"Dataset {dataset_id} already exists.")
        else:
            print(f"Failed to create dataset: {e}")
            return

    table_id = f"{dataset_id}.crowd_events"
    schema = [
        bigquery.SchemaField("zone_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("density", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    try:
        table = client.create_table(table, timeout=30)
        print(f"Created table {table.project}.{table.dataset_id}.{table.table_id}")
    except Exception as e:
        if "Already Exists" in str(e):
            print(f"Table {table_id} already exists.")
        else:
            print(f"Failed to create table: {e}")


if __name__ == "__main__":
    setup_bigquery()
