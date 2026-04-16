import httpx
import json

def setup_gcp_rest():
    project_id = "stadiumchecker"
    token = "ya29.REPLACED_FOR_SECURITY"  # Sensitive token removed
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Create BigQuery Dataset
    print("Creating BigQuery dataset 'analytics'...")
    dataset_url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/datasets"
    dataset_body = {
        "datasetReference": {"datasetId": "analytics"},
        "location": "US"
    }
    
    resp = httpx.post(dataset_url, headers=headers, json=dataset_body)
    if resp.status_code == 200:
        print("Dataset created successfully.")
    elif resp.status_code == 409:
        print("Dataset already exists.")
    else:
        print(f"Failed to create dataset: {resp.status_code} - {resp.text}")
        # Continue anyway as it might have existed

    # 2. Create BigQuery Table
    print("Creating BigQuery table 'crowd_events'...")
    table_url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/datasets/analytics/tables"
    table_body = {
        "tableReference": {"tableId": "crowd_events"},
        "schema": {
            "fields": [
                {"name": "zone_id", "type": "STRING", "mode": "REQUIRED"},
                {"name": "density", "type": "INTEGER", "mode": "REQUIRED"},
                {"name": "timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"}
            ]
        }
    }
    
    resp = httpx.post(table_url, headers=headers, json=table_body)
    if resp.status_code == 200:
        print("Table created successfully.")
    elif resp.status_code == 409:
        print("Table already exists.")
    else:
        print(f"Failed to create table: {resp.status_code} - {resp.text}")

    # 3. Initialize Firestore (Native Mode)
    print("Initializing Firestore database...")
    # POST https://firestore.googleapis.com/v1/projects/{project_id}/databases?databaseId=(default)
    # The parent for this is projects/{project_id}
    firestore_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases"
    # Query param ?databaseId=(default)
    firestore_body = {
        "name": f"projects/{project_id}/databases/(default)",
        "locationId": "us-central1",
        "type": "FIRESTORE_NATIVE"
    }
    # Note: creating (default) database is a POST to the collection
    resp = httpx.post(f"{firestore_url}?databaseId=(default)", headers=headers, json=firestore_body)
    if resp.status_code in (200, 201):
        print("Firestore initialization started successfully.")
    elif resp.status_code == 409:
        print("Firestore already initialized.")
    else:
        print(f"Failed to initialize Firestore: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    setup_gcp_rest()
