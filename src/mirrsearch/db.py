from dataclasses import dataclass
from typing import List, Dict, Any
import os
import json
import psycopg2
from opensearchpy import OpenSearch

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from dotenv import load_dotenv
except ImportError:
    LOAD_DOTENV = None
else:
    LOAD_DOTENV = load_dotenv


@dataclass(frozen=True)
class DBLayer:
    """
    DB layer for connecting to PostgreSQL and returning data.
    """
    conn: Any = None

    def search(self, query: str, filter_param: str = None) -> List[Dict[str, Any]]:
        if self.conn is None:
            raise RuntimeError("No database connection available. Set USE_POSTGRES=true and provide valid credentials.")

        q = (query or "").strip()
        sql = """
            SELECT docket_id, document_title, agency_id, document_type
            FROM documents
            WHERE (docket_id ILIKE %s OR document_title ILIKE %s)
        """
        params = [f"%{q}%", f"%{q}%"] if q else ["%%", "%%"]
        if filter_param:
            sql += " AND document_type = %s"
            params.append(filter_param)

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return [
                {
                    "docket_id": row[0],
                    "title": row[1],
                    "agency_id": row[2],
                    "document_type": row[3],
                }
                for row in cur.fetchall()
            ]


def _get_secrets_from_aws() -> Dict[str, str]:
    """
    Fetch database credentials from AWS Secrets Manager.
    Used when running on EC2 with USE_AWS_SECRETS=true.
    """
    if boto3 is None:
        raise ImportError("boto3 is required to use AWS Secrets Manager. Run: pip install boto3")

    client = boto3.client(
        "secretsmanager",
        region_name="YOUR_REGION"  # TODO: replace with your region e.g. "us-east-1"
    )
    response = client.get_secret_value(
        SecretId="YOUR_SECRET_NAME"  # TODO: replace with your secret name e.g. "dev/mirrulations/postgres"
    )
    return json.loads(response["SecretString"])


def get_postgres_connection() -> DBLayer:
    """
    Connect to PostgreSQL using either:
    - AWS Secrets Manager (if USE_AWS_SECRETS=true) — used on EC2
    - .env file via environment variables (default) — used locally
    """
    use_aws_secrets = os.getenv("USE_AWS_SECRETS", "").lower() in {"1", "true", "yes", "on"}

    if use_aws_secrets:
        creds = _get_secrets_from_aws()
        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            database=creds["db"],
            user=creds["username"],
            password=creds["password"]
        )
    else:
        if LOAD_DOTENV is not None:
            LOAD_DOTENV()
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )

    return DBLayer(conn)


def get_db() -> DBLayer:
    """
    Return the default DB layer for the app.
    - Locally: reads from .env file
    - On EC2: reads from AWS Secrets Manager when USE_AWS_SECRETS=true
    """
    if LOAD_DOTENV is not None:
        LOAD_DOTENV()

    use_postgres = os.getenv("USE_POSTGRES", "").lower() in {"1", "true", "yes", "on"}

    if use_postgres:
        return get_postgres_connection()

    raise RuntimeError("USE_POSTGRES is not set. Add USE_POSTGRES=true to your .env file.")


def get_opensearch_connection() -> OpenSearch:
    client = OpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        use_ssl=False,
        verify_certs=False,
    )
    return client
