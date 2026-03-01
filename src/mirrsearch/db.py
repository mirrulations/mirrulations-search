# pylint: disable=duplicate-code
import json
from dataclasses import dataclass
from typing import List, Dict, Any
import os
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
    conn: Any = None

    def search(
            self,
            query: str,
            document_type_param: str = None,
            agency: str = None,
            cfr_part_param: str = None) \
            -> List[Dict[str, Any]]:
        if self.conn is None:
            return []
        return self._search_postgres(query, document_type_param, agency, cfr_part_param)

    def _search_postgres(  # pylint: disable=unused-argument
            self,
            query: str,
            document_type_param: str = None,
            agency: str = None,
            cfr_part_param: str = None) \
            -> List[Dict[str, Any]]:
        sql = """
            SELECT d.docket_id, d.document_title, NULL AS cfrpart, d.agency_id, d.document_type
            FROM documents d
            -- LEFT JOIN cfrparts c ON d.document_id = c.document_id
            WHERE (d.docket_id ILIKE %s OR d.document_title ILIKE %s)
        """
        params = ([f"%{(query or '').strip().lower()}%"] * 2
                  if (query or "").strip()
                  else ["%%", "%%"])

        if document_type_param:
            sql += " AND d.document_type = %s"
            params.append(document_type_param)

        # cfr_part_param filter commented out until cfrparts table is available in RDS
        # if cfr_part_param:
        #     sql += " AND c.cfrpart ILIKE %s"
        #     params.append(f"%{cfr_part_param}%")

        if agency:
            sql += " AND d.agency_id ILIKE %s"
            params.append(f"%{agency}%")

        sql += " LIMIT 50"

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return [
                {
                    "docket_id": row[0],
                    "title": row[1],
                    "cfrPart": row[2],
                    "agency_id": row[3],
                    "document_type": row[4],
                }
                for row in cur.fetchall()
            ]


def _get_secrets_from_aws() -> Dict[str, str]:
    if boto3 is None:
        raise ImportError("boto3 is required to use AWS Secrets Manager.")

    client = boto3.client(
        "secretsmanager",
        region_name="YOUR_REGION"
    )
    response = client.get_secret_value(
        SecretId="YOUR_SECRET_NAME"
    )
    return json.loads(response["SecretString"])


def get_postgres_connection() -> DBLayer:
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
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "your_db"),
            user=os.getenv("DB_USER", "your_user"),
            password=os.getenv("DB_PASSWORD", "your_password")
        )

    return DBLayer(conn)


def get_db() -> DBLayer:
    """
    Return the default DB layer for the app.
    """
    if LOAD_DOTENV is not None:
        LOAD_DOTENV()

    use_postgres = os.getenv("USE_POSTGRES", "").lower() in {"1", "true", "yes", "on"}

    if use_postgres:
        return get_postgres_connection()

    return DBLayer()


def get_opensearch_connection() -> OpenSearch:
    client = OpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        use_ssl=False,
        verify_certs=False,
    )
    return client
