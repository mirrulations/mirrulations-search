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
            docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None) \
            -> List[Dict[str, Any]]:
        if self.conn is None:
            return []
        docket_matches = self._search_dockets_postgres(
            query, docket_type_param, agency, cfr_part_param
            )
        #document_matches = self._search_documents_postgres(
            #query, docket_type_param, agency, cfr_part_param
            #)
        return docket_matches

    def _search_dockets_postgres(  # pylint: disable=too-many-locals
            self, query: str, docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT DISTINCT
                d.docket_id,
                d.docket_title,
                d.agency_id,
                d.docket_type,
                d.modify_date,
                cp.title,
                cp.cfrPart,
                l.link
            FROM dockets d
            JOIN documents doc ON doc.docket_id = d.docket_id
            LEFT JOIN cfrparts cp ON cp.document_id = doc.document_id
            LEFT JOIN links l ON l.title = cp.title AND l.cfrPart = cp.cfrPart
            WHERE d.docket_title ILIKE %s
        """
        params = [f"%{(query or '').strip().lower()}%"]

        if docket_type_param:
            sql += " AND d.docket_type = %s"
            params.append(docket_type_param)

        if agency:
            clauses = " OR ".join("d.agency_id ILIKE %s" for _ in agency)
            sql += f" AND ({clauses})"
            params.extend(f"%{a}%" for a in agency)

        if cfr_part_param:
            clauses = " OR ".join("cp.cfrPart ILIKE %s" for _ in cfr_part_param)
            sql += f" AND ({clauses})"
            params.extend(f"%{c}%" for c in cfr_part_param)

        sql += " ORDER BY d.modify_date DESC, d.docket_id, cp.title, cp.cfrPart LIMIT 50"

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            dockets = {}
            for row in cur.fetchall():
                self._process_docket_row(dockets, row)
            return [
                {**d, "cfr_refs": list(d["cfr_refs"].values())}
                for d in dockets.values()
            ]

    @staticmethod
    def _process_docket_row(dockets, row):
        docket_id = row[0]
        if docket_id not in dockets:
            dockets[docket_id] = {
                "docket_id": row[0],
                "docket_title": row[1],
                "agency_id": row[2],
                "docket_type": row[3],
                "modify_date": row[4],
                "cfr_refs": {}
            }
        title, cfr_part, link = row[5], row[6], row[7]
        if title is not None and cfr_part is not None:
            if title not in dockets[docket_id]["cfr_refs"]:
                dockets[docket_id]["cfr_refs"][title] = {
                    "title": title,
                    "cfrParts": {}
                }
            dockets[docket_id]["cfr_refs"][title]["cfrParts"][cfr_part] = link

    def _search_documents_postgres(  # pylint: disable=too-many-locals
            self, query: str, docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT DISTINCT
                doc.document_id,
                doc.document_title,
                doc.agency_id,
                doc.document_type,
                doc.posted_date,
                doc.docket_id,
                cp.title,
                cp.cfrPart,
                l.link
            FROM documents doc
            LEFT JOIN cfrparts cp ON cp.document_id = doc.document_id
            LEFT JOIN links l ON l.title = cp.title AND l.cfrPart = cp.cfrPart
            WHERE doc.document_title ILIKE %s
        """
        params = [f"%{(query or '').strip().lower()}%"]

        if docket_type_param:
            sql += " AND doc.document_type = %s"
            params.append(docket_type_param)

        if agency:
            clauses = " OR ".join("doc.agency_id ILIKE %s" for _ in agency)
            sql += f" AND ({clauses})"
            params.extend(f"%{a}%" for a in agency)

        if cfr_part_param:
            clauses = " OR ".join("cp.cfrPart ILIKE %s" for _ in cfr_part_param)
            sql += f" AND ({clauses})"
            params.extend(f"%{c}%" for c in cfr_part_param)

        sql += " ORDER BY doc.posted_date DESC, doc.document_id, cp.title, cp.cfrPart LIMIT 50"

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            documents = {}
            for row in cur.fetchall():
                self._process_document_row(documents, row)
            return [
                {**d, "cfr_refs": list(d["cfr_refs"].values())}
                for d in documents.values()
            ]

    @staticmethod
    def _process_document_row(documents, row):
        document_id = row[0]
        if document_id not in documents:
            documents[document_id] = {
                "document_id": row[0],
                "document_title": row[1],
                "agency_id": row[2],
                "document_type": row[3],
                "posted_date": row[4],
                "docket_id": row[5],
                "cfr_refs": {}
            }
        title, cfr_part, link = row[6], row[7], row[8]
        if title is not None and cfr_part is not None:
            if title not in documents[document_id]["cfr_refs"]:
                documents[document_id]["cfr_refs"][title] = {
                    "title": title,
                    "cfrParts": {}
                }
            documents[document_id]["cfr_refs"][title]["cfrParts"][cfr_part] = link


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
    if LOAD_DOTENV is not None:
        LOAD_DOTENV()
    try:
        return get_postgres_connection()
    except psycopg2.OperationalError:
        return DBLayer()


def get_opensearch_connection() -> OpenSearch:
    if LOAD_DOTENV is not None:
        LOAD_DOTENV()
    return OpenSearch(
        hosts=[{
            "host": os.getenv("OPENSEARCH_HOST", "localhost"),
            "port": int(os.getenv("OPENSEARCH_PORT", "9200")),
        }],
        use_ssl=False,
        verify_certs=False,
    )
