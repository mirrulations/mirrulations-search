from dataclasses import dataclass
from typing import List, Dict, Any
import os
import psycopg2
from opensearchpy import OpenSearch
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
            return []

        q = (query or "").strip()
        sql = """
            SELECT docket_id, title, cfr_part, agency_id, document_type
            FROM document
            WHERE (docket_id ILIKE %s OR title ILIKE %s)
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
                    "cfrPart": row[2],
                    "agency_id": row[3],
                    "document_type": row[4],
                }
                for row in cur.fetchall()
            ]


def get_postgres_connection() -> DBLayer:
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
