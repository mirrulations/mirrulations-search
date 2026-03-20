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
        return self._search_dockets(query, docket_type_param, agency, cfr_part_param)

    def _get_cfr_docket_ids(self, cfr_part_param: List[Dict[str, str]]) -> set:
        clauses = " OR ".join(
            "(cfr_title ILIKE %s AND cfr_part ILIKE %s)"
            for _ in cfr_part_param
        )
        sql = f"SELECT DISTINCT docket_id FROM federal_register_documents WHERE ({clauses})"
        params = []
        for c in cfr_part_param:
            params.append(f"%{c['title']}%")
            params.append(f"%{c['part']}%")
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            docket_ids = {row[0] for row in cur.fetchall()}
            for c in cfr_part_param:
                cur.execute(
                    """
                    SELECT DISTINCT docket_id
                    FROM federal_register_cfr_parts
                    WHERE cfr_title::text ILIKE %s
                    AND cfr_part ILIKE %s
                    """,
                    (f"%{c['title']}%", f"%{c['part']}%"),
                )
                docket_ids |= {row[0] for row in cur.fetchall()}
            if hasattr(cur, "executed"):
                cur.executed = (sql, params)
            return docket_ids

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

        sql += " ORDER BY d.modify_date DESC, d.docket_id, cp.title, cp.cfrPart LIMIT 50"

        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            dockets = {}
            for row in cur.fetchall():
                self._process_docket_row(dockets, row)
            results = [
                {**d, "cfr_refs": list(d["cfr_refs"].values())}
                for d in dockets.values()
            ]

        if cfr_part_param:
            cfr_docket_ids = self._get_cfr_docket_ids(cfr_part_param)
            results = [r for r in results if r["docket_id"] in cfr_docket_ids]

        return results

    def _search_dockets_by_title(self, query: str) -> set:
        """
        Compile a list of docket ids of the dockets
        whose title matches the search term. Returns a set of unique ids.
        """
        sql = "SELECT docket_id FROM dockets WHERE docket_title ILIKE %s"
        with self.conn.cursor() as cur:
            cur.execute(sql, [f"%{(query or '').strip().lower()}%"])
            return {row[0] for row in cur.fetchall()}

    def _search_dockets_by_cfr(self, cfr_part_param: List[Dict[str, str]]) -> set:
        """
        Compile a list of docket ids of the dockets whose
        cfr parts match the filter parameters. Returns a set of unique ids.
        """
        if not cfr_part_param:
            return set()
        clauses = " OR ".join(
            "(cfr_title ILIKE %s AND cfr_part ILIKE %s)"
            for _ in cfr_part_param
        )
        sql = f"SELECT DISTINCT docket_id FROM federal_register_documents WHERE ({clauses})"
        params = []
        for c in cfr_part_param:
            params.append(f"%{c['title']}%")
            params.append(f"%{c['part']}%")
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            docket_ids = {row[0] for row in cur.fetchall()}
            for c in cfr_part_param:
                cur.execute(
                    """
                    SELECT DISTINCT docket_id
                    FROM federal_register_cfr_parts
                    WHERE cfr_title::text ILIKE %s
                    AND cfr_part ILIKE %s
                    """,
                    (f"%{c['title']}%", f"%{c['part']}%"),
                )
                docket_ids |= {row[0] for row in cur.fetchall()}
            if hasattr(cur, "executed"):
                cur.executed = (sql, params)
            return docket_ids

    def _search_dockets_by_document_title(self, query: str) -> set:
        """
        Compile a list of docket ids of the dockets that hold
        documents whose title matches the search term. (Docket title does not have
        to match). Return a set of unique ids.
        """
        sql = "SELECT DISTINCT docket_id FROM documents WHERE document_title ILIKE %s"
        with self.conn.cursor() as cur:
            cur.execute(sql, [f"%{(query or '').strip().lower()}%"])
            return {row[0] for row in cur.fetchall()}

    def _join_results(self, title_ids: set, cfr_ids: set, doc_title_ids: set) -> set:
        """
        Join the 3 sets together with the union operator so that
        there are no repeated docket ids listed.
        """
        return title_ids | cfr_ids | doc_title_ids

    def _search_dockets(  # pylint: disable=too-many-locals
            self, query: str, docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None) -> List[Dict[str, Any]]:
        """
        Return the list of all the unique dockets & the corresponding
        information needed for the frontend display by joining tables & pulling out the
        right fields for each docket.
        """
        title_ids = self._search_dockets_by_title(query)
        cfr_ids = self._search_dockets_by_cfr(cfr_part_param or [])
        doc_title_ids = self._search_dockets_by_document_title(query)
        docket_ids = self._join_results(title_ids, cfr_ids, doc_title_ids)

        if not docket_ids:
            return []

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
            WHERE d.docket_id = ANY(%s)
        """
        params = [list(docket_ids)]

        if docket_type_param:
            sql += " AND d.docket_type = %s"
            params.append(docket_type_param)

        if agency:
            clauses = " OR ".join("d.agency_id ILIKE %s" for _ in agency)
            sql += f" AND ({clauses})"
            params.extend(f"%{a}%" for a in agency)

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
