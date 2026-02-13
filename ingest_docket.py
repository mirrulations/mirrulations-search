"""
ingest_docket.py

This script:
1. Instantiates the DBLayer (currently using dummy in-memory data).
2. Searches for all documents matching a given docket_id.
3. Indexes those records into a local OpenSearch instance.

This is currently using dummy data from DBLayer._items().
Later, DBLayer.search() can be modified to query PostgreSQL
without changing this ingestion script.
"""

from src.mirrsearch.db import DBLayer, get_opensearch_connection

INDEX_NAME = "docket"
DOCKET_ID = "CMS-2025-0240"


def create_index_if_not_exists(client):
    """
    Creates the OpenSearch index if it does not already exist.
    """
    if not client.indices.exists(index=INDEX_NAME):
        client.indices.create(index=INDEX_NAME)
        print(f"Created index: {INDEX_NAME}")
    else:
        print(f"Index '{INDEX_NAME}' already exists.")


def ingest_one_docket(docket_id: str):
    """
    Pulls records from DBLayer (currently dummy data)
    and indexes them into OpenSearch.
    """

    # Since DBLayer expects a conn but dummy mode doesn't use it,
    # we pass None for now.
    db = DBLayer(conn=None)

    # Connect to local OpenSearch
    client = get_opensearch_connection()

    # Ensure index exists
    create_index_if_not_exists(client)

    # Fetch records from DBLayer
    records = db.search(docket_id)

    if not records:
        print(f"No records found for docket_id={docket_id}")
        return

    # Index each record into OpenSearch
    for i, record in enumerate(records):
        doc_id = f"{docket_id}-{i}"

        client.index(
            index=INDEX_NAME,
            id=doc_id,
            body=record
        )

    print(f"Ingested {len(records)} records into OpenSearch.")


if __name__ == "__main__":
    ingest_one_docket(DOCKET_ID)
