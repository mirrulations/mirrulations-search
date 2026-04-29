# pylint: disable=too-many-lines
import json
import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Dict, Any, Set, Optional
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from opensearchpy import OpenSearch

log = logging.getLogger(__name__)

try:
    import requests
    from requests_aws4auth import AWS4Auth
except ImportError:
    requests = None
    AWS4Auth = None

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


def _parse_opensearch_port_env(var_name: str, default: int = 9200) -> int:
    """Parse OPENSEARCH_PORT safely — empty or invalid values fall back to default."""
    raw = (os.getenv(var_name) or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError:
        return default
    if port < 1 or port > 65535:
        return default
    return port


def _env_flag_true(var_name: str) -> bool:
    return (os.getenv(var_name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _cfr_part_item_pattern(item: Any) -> str:
    """Single CFR filter value → lowercase substring, or '' if absent."""
    if isinstance(item, dict):
        return (item.get("part") or "").strip().lower()
    if item is None:
        return ""
    return str(item).strip().lower()


def cfr_part_filter_patterns(cfr_part_param) -> List[str]:
    """
    Build lowercase substring patterns for CFR part filtering.

    Accepts plain strings or dicts with a ``part`` key from the UI.
    """
    if not cfr_part_param:
        return []
    return [p for p in (_cfr_part_item_pattern(i) for i in cfr_part_param) if p]


def _cfr_exact_title_part_pairs(cfr_part_param) -> List[tuple]:
    """Extract exact CFR (title, part) pairs from dict-style filter payloads."""
    if not cfr_part_param:
        return []
    pairs: List[tuple] = []
    for item in cfr_part_param:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        part = str(item.get("part") or "").strip()
        if title and part:
            pairs.append((title, part))
    return pairs


def _parse_positive_int_env(var_name: str, default: int) -> int:
    """Parse env var as positive int, falling back to default."""
    raw = (os.getenv(var_name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _opensearch_match_docket_bucket_size() -> int:
    """How many docket buckets to request for corpus-wide match aggregations."""
    return _parse_positive_int_env("OPENSEARCH_MATCH_DOCKET_BUCKET_SIZE", 1000)


# AOSS 429 resilience: track recent throttle events and short-circuit AOSS
# when the same query stream keeps overwhelming OCU capacity.
_AOSS_FAIL_WINDOW_SEC = 30.0
_AOSS_FAIL_THRESHOLD = 2
_AOSS_BREAKER_COOLDOWN_SEC = 30.0
_AOSS_RETRY_BACKOFF_SEC = 0.25

_aoss_failures: "deque[float]" = deque(maxlen=_AOSS_FAIL_THRESHOLD)
_aoss_breaker_open_until: float = 0.0  # pylint: disable=invalid-name


def _is_429(exc: BaseException) -> bool:
    msg = str(exc)
    return "429" in msg or "Too Many Requests" in msg


def _aoss_breaker_is_open() -> bool:
    return time.monotonic() < _aoss_breaker_open_until


def _record_aoss_429() -> None:
    global _aoss_breaker_open_until  # pylint: disable=global-statement
    now = time.monotonic()
    _aoss_failures.append(now)
    recent = [t for t in _aoss_failures if now - t <= _AOSS_FAIL_WINDOW_SEC]
    if len(recent) >= _AOSS_FAIL_THRESHOLD:
        _aoss_breaker_open_until = now + _AOSS_BREAKER_COOLDOWN_SEC


def _reset_aoss_breaker_for_tests() -> None:
    global _aoss_breaker_open_until  # pylint: disable=global-statement
    _aoss_failures.clear()
    _aoss_breaker_open_until = 0.0



# ---------------------------------------------------------------------------
# SQLAlchemy engine — created once at module level, shared across all requests.
#
#   pool_pre_ping=True  — before handing out a connection, SQLAlchemy runs
#                         SELECT 1. If the connection is dead it discards it
#                         and opens a fresh one transparently.
#   pool_recycle=1800   — recycle connections older than 30 minutes so RDS's
#                         idle-connection timeout never kills them silently.
#   pool_size / max_overflow — tune to match your Gunicorn worker count.
# ---------------------------------------------------------------------------
_ENGINE: Engine = None


def _build_engine(dsn: str) -> Engine:
    return create_engine(
        dsn,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=5,
        connect_args={
            "connect_timeout": 5,
        },
    )


def _get_engine() -> Engine:  # pylint: disable=too-many-statements
    """Return the shared SQLAlchemy engine, creating it on first call."""
    global _ENGINE  # pylint: disable=global-statement
    if _ENGINE is not None:
        return _ENGINE

    use_aws_secrets = os.getenv("USE_AWS_SECRETS", "").lower() in {"1", "true", "yes", "on"}
    if use_aws_secrets:
        creds = _get_secrets_from_aws()
        dsn = (
            f"postgresql+psycopg2://{creds['username']}:{creds['password']}"
            f"@{creds['host']}:{creds['port']}/{creds['db']}"
        )
    else:
        if LOAD_DOTENV is not None:
            LOAD_DOTENV()
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "your_db")
        user = os.getenv("DB_USER", "your_user")
        password = os.getenv("DB_PASSWORD", "your_password")
        dsn = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    _ENGINE = _build_engine(dsn)
    return _ENGINE


@dataclass(frozen=True)
class DBLayer:  # pylint: disable=too-many-public-methods
    """
    All database methods now use SQLAlchemy's connection pool via _get_engine().

    self.engine holds the shared Engine. Every method checks `self.engine is None`
    the same way the original checked `self.conn is None`, so the rest of the app
    sees no interface change at all.
    """
    engine: Any = None

    # ------------------------------------------------------------------
    # Internal helpers — every SQL method goes through one of these.
    # SQLAlchemy's pool_pre_ping already handles dead-connection detection;
    # engine.begin() handles automatic rollback on failure.
    # ------------------------------------------------------------------
    def _run(self, sql: str, params: dict = None):
        """
        Execute a raw SQL string with the engine's connection pool.
        Returns all rows as a list of tuples.
        Uses :name style params (SQLAlchemy text() requirement).
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()

    def _run_write(self, sql: str, params: dict = None) -> int:
        """
        Execute a write (INSERT/UPDATE/DELETE) and commit.
        Returns rowcount.
        engine.begin() auto-commits on success and auto-rolls back on error.
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.rowcount

    def _run_returning(self, sql: str, params: dict = None):
        """
        Execute a write with RETURNING and commit.
        Returns the first column of the first row.
        engine.begin() auto-commits on success and auto-rolls back on error.
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchone()[0]

    # ------------------------------------------------------------------
    # All methods below are identical in behaviour to the original.
    # The only change is cursor/execute → _run / _run_write / _run_returning,
    # and %s params → :name params (SQLAlchemy text() style).
    # ------------------------------------------------------------------

    def search(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
            self,
            query: str,
            docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None,
            start_date: str = None,
            end_date: str = None,
            exact_docket_id: str = None) \
            -> List[Dict[str, Any]]:
        if self.engine is None:
            return []
        results = self._search_dockets_postgres(
            query, docket_type_param, agency, cfr_part_param, start_date, end_date,
            exact_docket_id=exact_docket_id,
        )
        exact_pairs = _cfr_exact_title_part_pairs(cfr_part_param)
        if not exact_pairs:
            return results
        allowed = self._get_cfr_docket_ids(exact_pairs)
        return [row for row in results if row["docket_id"] in allowed]

    def _get_cfr_docket_ids(self, cfr_pairs: List[tuple]) -> Set[str]:  # pylint: disable=too-many-locals
        """Return docket IDs matching exact CFR title+part pairs."""
        if self.engine is None or not cfr_pairs:
            return set()
        clauses = " OR ".join(
            f"(cp.title = :title_{i} AND cp.cfrPart = :part_{i})"
            for i in range(len(cfr_pairs))
        )
        sql = f"""
            SELECT DISTINCT d.docket_id
            FROM documents d
            JOIN cfrparts cp ON cp.frdocnum = d.frdocnum
            WHERE ({clauses})
        """
        params = {}
        for i, (title, part) in enumerate(cfr_pairs):
            params[f"title_{i}"] = title
            params[f"part_{i}"] = part
        rows = self._run(sql, params)
        return {row[0] for row in rows}

    def _search_dockets_postgres(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
            self, query: str, docket_type_param: str = None,
            agency: List[str] = None,
            cfr_part_param: List[str] = None,
            start_date: str = None,
            end_date: str = None,
            exact_docket_id: str = None) -> List[Dict[str, Any]]:
        # Agency rule codes like CMS-1849-P aren't stored in dockets at all;
        # they live in federal_register_documents.docket_ids and the regs.gov
        # docket sits in document_id with a trailing -NNNN we strip off.
        fr_clause = ""
        if exact_docket_id:
            fr_clause = (
                " OR d.docket_id IN ("
                "SELECT regexp_replace(fr.document_id, '-[0-9]+$', '') "
                "FROM federal_register_documents fr "
                "WHERE EXISTS (SELECT 1 FROM unnest(fr.docket_ids) e "
                "WHERE e ILIKE :exact_pattern))"
            )
        sql = f"""
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
            LEFT JOIN cfrparts cp ON cp.frdocnum = doc.frdocnum
            LEFT JOIN links l ON l.title = cp.title AND l.cfrPart = cp.cfrPart
            WHERE (d.docket_title ILIKE :query OR d.docket_id ILIKE :query{fr_clause})
        """
        params: Dict[str, Any] = {"query": f"%{(query or '').strip().lower()}%"}
        if exact_docket_id:
            params["exact_pattern"] = f"{exact_docket_id}%"

        if docket_type_param:
            sql += " AND d.docket_type = :docket_type"
            params["docket_type"] = docket_type_param

        if agency:
            clauses = " OR ".join(f"d.agency_id ILIKE :agency_{i}" for i in range(len(agency)))
            sql += f" AND ({clauses})"
            for i, a in enumerate(agency):
                params[f"agency_{i}"] = f"%{a}%"

        if start_date:
            sql += " AND CAST(d.modify_date AS date) >= CAST(:start_date AS date)"
            params["start_date"] = start_date

        if end_date:
            sql += " AND CAST(d.modify_date AS date) <= CAST(:end_date AS date)"
            params["end_date"] = end_date

        cfr_patterns = cfr_part_filter_patterns(cfr_part_param)
        if cfr_patterns:
            clauses = " OR ".join(f"cp3.cfrPart = :cfr_{i}" for i in range(len(cfr_patterns)))
            sql += (
                " AND EXISTS ("
                "SELECT 1 FROM documents d3 "
                "JOIN cfrparts cp3 ON cp3.frdocnum = d3.frdocnum "
                "WHERE d3.docket_id = d.docket_id "
                f"AND ({clauses})"
                ")"
            )
            for i, p in enumerate(cfr_patterns):
                params[f"cfr_{i}"] = p

        exact_pairs = _cfr_exact_title_part_pairs(cfr_part_param)
        if exact_pairs:
            exact_clauses = " OR ".join(
                f"(cp2.title = :etitle_{i} AND cp2.cfrPart = :epart_{i})"
                for i in range(len(exact_pairs))
            )
            sql += (
                " AND EXISTS ("
                "SELECT 1 FROM documents d2 "
                "JOIN cfrparts cp2 ON cp2.frdocnum = d2.frdocnum "
                "WHERE d2.docket_id = d.docket_id "
                f"AND ({exact_clauses})"
                ")"
            )
            for i, (title, part) in enumerate(exact_pairs):
                params[f"etitle_{i}"] = title
                params[f"epart_{i}"] = part

        sql += " ORDER BY d.modify_date DESC, d.docket_id, cp.title, cp.cfrPart LIMIT 50"

        rows = self._run(sql, params)
        dockets = {}
        for row in rows:
            self._process_docket_row(dockets, row)
        return [
            {**d, "cfr_refs": list(d["cfr_refs"].values())}
            for d in dockets.values()
        ]

    def get_dockets_by_ids(self, docket_ids: List[str]) -> List[Dict[str, Any]]:
        if self.engine is None or not docket_ids:
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
            LEFT JOIN cfrparts cp ON cp.frdocnum = doc.frdocnum
            LEFT JOIN links l ON l.title = cp.title AND l.cfrPart = cp.cfrPart
            WHERE d.docket_id = ANY(:docket_ids)
            ORDER BY d.modify_date DESC, d.docket_id, cp.title, cp.cfrPart
        """
        rows = self._run(sql, {"docket_ids": list(docket_ids)})
        dockets = {}
        for row in rows:
            self._process_docket_row(dockets, row)
        return [
            {**d, "cfr_refs": list(d["cfr_refs"].values())}
            for d in dockets.values()
        ]
    def get_dockets_by_ids_filtered(self, docket_ids: List[str], docket_type_param: str = None,#pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals, too-many-branches, too-many-statements
        agency: List[str] = None, cfr_part_param: List[str] = None, start_date: str = None,
        end_date: str = None, ) -> List[Dict[str, Any]]:
        if self.engine is None or not docket_ids:
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
            LEFT JOIN cfrparts cp ON cp.frdocnum = doc.frdocnum
            LEFT JOIN links l ON l.title = cp.title AND l.cfrPart = cp.cfrPart
            WHERE d.docket_id = ANY(:docket_ids)
        """
        params: Dict[str, Any] = {"docket_ids": list(docket_ids)}

        if docket_type_param:
            sql += " AND d.docket_type = :docket_type"
            params["docket_type"] = docket_type_param

        if agency:
            clauses = " OR ".join(f"d.agency_id ILIKE :agency_{i}" for i in range(len(agency)))
            sql += f" AND ({clauses})"
            for i, a in enumerate(agency):
                params[f"agency_{i}"] = f"%{a}%"

        if start_date:
            sql += " AND CAST(d.modify_date AS date) >= CAST(:start_date AS date)"
            params["start_date"] = start_date

        if end_date:
            sql += " AND CAST(d.modify_date AS date) <= CAST(:end_date AS date)"
            params["end_date"] = end_date

        cfr_patterns = cfr_part_filter_patterns(cfr_part_param)
        if cfr_patterns:
            clauses = " OR ".join(f"cp3.cfrPart = :cfr_{i}" for i in range(len(cfr_patterns)))
            sql += (
                " AND EXISTS ("
                "SELECT 1 FROM documents d3 "
                "JOIN cfrparts cp3 ON cp3.frdocnum = d3.frdocnum "
                "WHERE d3.docket_id = d.docket_id "
                f"AND ({clauses})"
                ")"
            )
            for i, p in enumerate(cfr_patterns):
                params[f"cfr_{i}"] = p

        exact_pairs = _cfr_exact_title_part_pairs(cfr_part_param)
        if exact_pairs:
            exact_clauses = " OR ".join(
                f"(cp2.title = :etitle_{i} AND cp2.cfrPart = :epart_{i})"
                for i in range(len(exact_pairs))
            )
            sql += (
                " AND EXISTS ("
                "SELECT 1 FROM documents d2 "
                "JOIN cfrparts cp2 ON cp2.frdocnum = d2.frdocnum "
                "WHERE d2.docket_id = d.docket_id "
                f"AND ({exact_clauses})"
                ")"
            )
            for i, (title, part) in enumerate(exact_pairs):
                params[f"etitle_{i}"] = title
                params[f"epart_{i}"] = part

        sql += " ORDER BY d.modify_date DESC, d.docket_id, cp.title, cp.cfrPart"

        rows = self._run(sql, params)
        dockets = {}
        for row in rows:
            self._process_docket_row(dockets, row)
        return [
            {**d, "cfr_refs": list(d["cfr_refs"].values())}
            for d in dockets.values()
        ]

    def get_agencies(self) -> List[str]:
        if self.engine is None:
            return []
        rows = self._run("SELECT DISTINCT agency_id FROM dockets ORDER BY agency_id")
        return [row[0] for row in rows]

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

    @staticmethod
    def _build_docket_agg_query(agg_name: str, match_clauses: List[Dict]) -> Dict:
        """Build a docket-bucketed aggregation query with an inner filter."""
        return {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "should": match_clauses,
                    "minimum_should_match": 1
                }
            },
            "aggs": {
                "by_docket": {
                    "terms": {
                        "field": "docketId.keyword",
                        "size": _opensearch_match_docket_bucket_size(),
                        "shard_size": 55000,
                        "order": {"_count": "desc"}
                    },
                    "aggs": {
                        agg_name: {
                            "filter": {
                                "bool": {
                                    "should": match_clauses,
                                    "minimum_should_match": 1
                                }
                            }
                        }
                    }
                }
            }
        }

    @staticmethod
    def _build_docket_agg_query_unique_comments(
            agg_name: str, match_clauses: List[Dict]) -> Dict:
        """Builds a docket-bucketed aggregation query with cardinality for unique comment counts"""
        return {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "should": match_clauses,
                    "minimum_should_match": 1
                }
            },
            "aggs": {
                "by_docket": {
                    "terms": {
                        "field": "docketId.keyword",
                        "size": _opensearch_match_docket_bucket_size(),
                        "shard_size": 55000,
                        "order": {"_count": "desc"}
                    },
                    "aggs": {
                        agg_name: {
                            "filter": {
                                "bool": {
                                    "should": match_clauses,
                                    "minimum_should_match": 1
                                }
                            },
                            "aggs": {
                                "unique_comments": {
                                    "cardinality": {
                                        "field": "commentId.keyword",
                                        "precision_threshold": 3000
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

    @staticmethod
    def _accumulate_counts(
            docket_counts: Dict, buckets: List, agg_name: str, count_key: str) -> None:
        """Add match counts from OpenSearch buckets into docket_counts in place."""
        for bucket in buckets:
            match_count = bucket[agg_name]["doc_count"]
            if match_count > 0:
                docket_id = str(bucket["key"])
                docket_counts.setdefault(
                    docket_id, {"document_match_count": 0, "comment_match_count": 0}
                )
                docket_counts[docket_id][count_key] += match_count

    def text_match_terms(
            self, terms: List[str], opensearch_client=None) -> List[Dict[str, Any]]:
        """Search OpenSearch for dockets matching terms across all indexes.

        Single-character terms (e.g. "a") match essentially every comment in
        the corpus and reliably time out the bucket aggregation, returning a
        503 to the user. For those, skip AOSS entirely — the SQL title search
        still runs and returns useful results. The 2-char threshold can be
        revisited if legitimately-short tokens like "AI" or "5G" become a
        common search.

        When the caller doesn't pass an opensearch_client (i.e. real requests),
        results are cached so pagination clicks for the same query return an
        identical hit list. Without this, per-call AOSS variance (one of the
        three aggregation queries occasionally erroring or timing out) caused
        total_results to drift between page navigations.
        """
        if any(len((t or "").strip()) < 2 for t in terms):
            return []
        if _aoss_breaker_is_open():
            return []
        if opensearch_client is not None:
            return self._run_text_match_queries(opensearch_client, terms)
        return self._cached_text_match_terms(tuple(terms))

    @lru_cache(maxsize=128)
    def _cached_text_match_terms(self, terms_tuple):
        return self._run_text_match_queries(
            get_opensearch_connection(), list(terms_tuple)
        )

    @staticmethod
    def _aoss_search(opensearch_client, index: str, body: Dict) -> Optional[Dict]:
        """Run an AOSS search; one 250ms retry on 429, isolate failures per index.

        Returns None when the index errors after retry. Records 429s for the
        circuit breaker so a sustained throttle stops piling on AOSS.
        """
        try:
            return opensearch_client.search(index=index, body=body)
        except Exception as exc:  # pylint: disable=broad-except
            if _is_429(exc):
                time.sleep(_AOSS_RETRY_BACKOFF_SEC)
                try:
                    return opensearch_client.search(index=index, body=body)
                except Exception as retry_exc:  # pylint: disable=broad-except
                    if _is_429(retry_exc):
                        _record_aoss_429()
                    log.warning("AOSS index %s failed after retry: %s", index, retry_exc)
                    return None
            log.warning("AOSS index %s failed: %s", index, exc)
            return None

    def _run_text_match_queries(  # pylint: disable=too-many-locals
            self, opensearch_client, terms: List[str]) -> List[Dict[str, Any]]:
        """Run the three OpenSearch queries in parallel and merge what came back.

        Each index call goes through ``_aoss_search`` so a 429 retry, the
        circuit breaker, and per-index isolation all still apply. Wall-clock
        time is roughly the slowest single query instead of the sum.
        """
        docket_counts: Dict = {}

        doc_match_clauses = [
            {"multi_match": {
                "query": t,
                "fields": ["title^2", "documentText"],
                "type": "best_fields",
                "tie_breaker": 0.3,
                "operator": "or"
            }}
            for t in terms
        ]
        comment_match_clauses = [{"match": {"commentText": t}} for t in terms]
        extracted_match_clauses = [{"match": {"extractedText": t}} for t in terms]

        queries = [
            ("documents_text",
             self._build_docket_agg_query("matching_docs", doc_match_clauses)),
            ("comments",
             self._build_docket_agg_query_unique_comments(
                 "matching_comments", comment_match_clauses)),
            ("comments_extracted_text",
             self._build_docket_agg_query_unique_comments(
                 "matching_extracted", extracted_match_clauses)),
        ]

        responses: Dict[str, Optional[Dict]] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._aoss_search, opensearch_client, index_name, body): index_name
                for index_name, body in queries
            }
            for future in futures:
                index_name = futures[future]
                responses[index_name] = future.result()

        doc_resp = responses["documents_text"]
        comment_resp = responses["comments"]
        extracted_resp = responses["comments_extracted_text"]

        if doc_resp is not None:
            self._accumulate_counts(
                docket_counts,
                doc_resp["aggregations"]["by_docket"]["buckets"],
                "matching_docs",
                "document_match_count"
            )

        comment_counts = (
            self._extract_cardinality_counts(comment_resp, "matching_comments")
            if comment_resp is not None else {}
        )
        extracted_counts = (
            self._extract_cardinality_counts(extracted_resp, "matching_extracted")
            if extracted_resp is not None else {}
        )
        for did in set(comment_counts) | set(extracted_counts):
            docket_counts.setdefault(
                did, {"document_match_count": 0, "comment_match_count": 0}
            )
            docket_counts[did]["comment_match_count"] = max(
                comment_counts.get(did, 0),
                extracted_counts.get(did, 0)
            )

        return [{"docket_id": did, **counts} for did, counts in docket_counts.items()]

    @staticmethod
    def _extract_cardinality_counts(resp: Dict, agg_name: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        buckets = (
            resp.get("aggregations", {}).get("by_docket", {}).get("buckets", [])
        )
        for bucket in buckets:
            inner = bucket.get(agg_name, {})
            if inner.get("doc_count", 0) > 0:
                value = inner.get("unique_comments", {}).get("value", 0)
                if value > 0:
                    counts[str(bucket["key"])] = value
        return counts

    @staticmethod
    def _comment_total_query(docket_ids: List[str]) -> Dict:
        """Aggregation: per docket, total comment count."""
        return {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"docketId.keyword": docket_ids}}
                    ]
                }
            },
            "aggs": {
                "by_docket": {
                    "terms": {"field": "docketId.keyword", "size": len(docket_ids)},
                    "aggs": {
                        "by_comment": {
                            "terms": {
                                "field": "commentId.keyword",
                                "size": 65535,
                            }
                        }
                    },
                }
            },
        }

    def get_docket_document_comment_totals( # pylint: disable=unused-argument
            self,
            docket_ids: List[str],
            opensearch_client=None
    ) -> Dict[str, Dict[str, int]]:
        """Return per-docket totals for documents and comments."""
        if not docket_ids:
            return {}
        try:
            return self._fetch_docket_totals(docket_ids)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Docket totals query failed: {e}")
            return {}

    def _fetch_docket_totals(
            self, docket_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """Fetch document and comment total counts from Postgres."""
        totals: Dict[str, Dict[str, int]] = {}
        if self.engine is None:
            return totals
        rows = self._run(
            "SELECT docket_id, COUNT(*) FROM documents "
            "WHERE docket_id = ANY(:docket_ids) GROUP BY docket_id",
            {"docket_ids": list(docket_ids)}
        )
        for docket_id, count in rows:
            totals[docket_id] = {"document_total_count": count, "comment_total_count": 0}
        rows = self._run(
            "SELECT docket_id, COUNT(*) FROM comments "
            "WHERE docket_id = ANY(:docket_ids) GROUP BY docket_id",
            {"docket_ids": list(docket_ids)}
        )
        for docket_id, count in rows:
            totals.setdefault(docket_id, {"document_total_count": 0, "comment_total_count": 0})
            totals[docket_id]["comment_total_count"] = count
        return totals


    def get_collections(self, user_email: str) -> List[Dict[str, Any]]:
        """Return all collections belonging to the given user."""
        if self.engine is None:
            return []
        sql = """
            SELECT c.collection_id, c.collection_name, c.user_email,
                   COALESCE(
                       json_agg(cd.docket_id) FILTER (WHERE cd.docket_id IS NOT NULL),
                       '[]'
                   ) AS docket_ids
            FROM collections c
            LEFT JOIN collection_dockets cd ON cd.collection_id = c.collection_id
            WHERE c.user_email = :user_email
            GROUP BY c.collection_id, c.collection_name, c.user_email
            ORDER BY c.collection_id
        """
        rows = self._run(sql, {"user_email": user_email})
        return [
            {
                "collection_id": row[0],
                "name": row[1],
                "user_email": row[2],
                "docket_ids": row[3] if isinstance(row[3], list) else []
            }
            for row in rows
        ]

    def create_collection(self, user_email: str, name: str) -> int:
        """Create a new collection for the user and return its id."""
        if self.engine is None:
            return -1
        self._run_write(
            "INSERT INTO users (email, name) VALUES (:email, :name) "
            "ON CONFLICT (email) DO NOTHING",
            {"email": user_email, "name": user_email}
        )
        return self._run_returning(
            "INSERT INTO collections (user_email, collection_name) "
            "VALUES (:user_email, :name) RETURNING collection_id",
            {"user_email": user_email, "name": name}
        )

    def delete_collection(self, collection_id: int, user_email: str) -> bool:
        """Delete a collection owned by the user. Returns True if deleted."""
        if self.engine is None:
            return False
        rowcount = self._run_write(
            "DELETE FROM collections WHERE collection_id = :cid AND user_email = :email",
            {"cid": collection_id, "email": user_email}
        )
        return rowcount > 0

    def add_docket_to_collection(
            self, collection_id: int, docket_id: str, user_email: str) -> bool:
        """Add a docket to a collection the user owns. Returns True if successful."""
        if self.engine is None:
            return False
        rows = self._run(
            "SELECT 1 FROM collections WHERE collection_id = :cid AND user_email = :email",
            {"cid": collection_id, "email": user_email}
        )
        if not rows:
            return False
        self._run_write(
            "INSERT INTO collection_dockets (collection_id, docket_id) "
            "VALUES (:cid, :docket_id) ON CONFLICT DO NOTHING",
            {"cid": collection_id, "docket_id": docket_id}
        )
        return True

    def remove_docket_from_collection(
            self, collection_id: int, docket_id: str, user_email: str) -> bool:
        """Remove a docket from a collection the user owns. Returns True if successful."""
        if self.engine is None:
            return False
        rows = self._run(
            "SELECT 1 FROM collections WHERE collection_id = :cid AND user_email = :email",
            {"cid": collection_id, "email": user_email}
        )
        if not rows:
            return False
        rowcount = self._run_write(
            "DELETE FROM collection_dockets WHERE collection_id = :cid AND docket_id = :docket_id",
            {"cid": collection_id, "docket_id": docket_id}
        )
        return rowcount > 0

    def create_download_job(  # pylint: disable=too-many-locals
            self,
            user_email: str,
            docket_ids: List[str],
            format: str = "zip",  # pylint: disable=redefined-builtin
            include_binaries: bool = False,
    ) -> str:
        """Create a download job and return the new job_id (UUID string)."""
        if self.engine is None:
            return ""
        self._run_write(
            "INSERT INTO users (email, name) VALUES (:email, :name) "
            "ON CONFLICT (email) DO NOTHING",
            {"email": user_email, "name": user_email}
        )
        job_id = self._run_returning(
            "INSERT INTO download_jobs (user_email, docket_ids, format, include_binaries) "
            "VALUES (:email, :docket_ids, :format, :include_binaries) RETURNING job_id",
            {
                "email": user_email,
                "docket_ids": docket_ids,
                "format": format,
                "include_binaries": include_binaries,
            }
        )
        return str(job_id)

    def get_download_job(self, job_id: str, user_email: str) -> Dict[str, Any]:
        """Return job details for the given job_id owned by user_email, or {}."""
        if self.engine is None:
            return {}
        sql = """
            SELECT job_id, user_email, docket_ids, format, include_binaries,
                   status, s3_path, created_at, updated_at, expires_at
            FROM download_jobs
            WHERE job_id = :job_id AND user_email = :email
        """
        rows = self._run(sql, {"job_id": job_id, "email": user_email})
        if not rows:
            return {}
        row = rows[0]
        return {
            "job_id": str(row[0]),
            "user_email": row[1],
            "docket_ids": row[2],
            "format": row[3],
            "include_binaries": row[4],
            "status": row[5],
            "s3_path": row[6],
            "created_at": row[7],
            "updated_at": row[8],
            "expires_at": row[9],
        }

    def update_download_job_status(
            self, job_id: str, status: str, s3_path: str = None) -> bool:
        """Update the status (and optionally s3_path) of a download job.

        Returns True if a row was updated.
        """
        if self.engine is None:
            return False
        rowcount = self._run_write(
            "UPDATE download_jobs SET status = :status, s3_path = :s3_path, "
            "updated_at = NOW() WHERE job_id = :job_id",
            {"status": status, "s3_path": s3_path, "job_id": job_id}
        )
        return rowcount > 0

    def get_expired_download_jobs(self) -> List[Dict[str, Any]]:
        """Return job_id and s3_path for all jobs where expires_at < NOW()."""
        if self.engine is None:
            return []
        rows = self._run(
            "SELECT job_id, s3_path FROM download_jobs WHERE expires_at < NOW()"
        )
        return [{"job_id": str(row[0]), "s3_path": row[1]} for row in rows]

    def get_download_s3_url(self, job_id: str, user_email: str) -> Optional[str]:
        """Return a presigned S3 URL for the given job, or local path if in dev mode."""
        if self.engine is None:
            return None
        job = self.get_download_job(job_id, user_email)
        s3_path = job.get("s3_path") if job else None
        if not s3_path:
            return None
        if s3_path.startswith("local://"):
            return s3_path[len("local://"):]
        return self._presign_s3_url(s3_path)

    def _presign_s3_url(self, s3_path: str) -> Optional[str]:
        """Generate a presigned URL from an s3:// path, or None if invalid."""
        if boto3 is None or not s3_path.startswith("s3://"):
            return None
        bucket, _, key = s3_path[len("s3://"):].partition("/")
        if not bucket or not key:
            return None
        return boto3.client("s3").generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,
        )

    def prune_expired_download_jobs(self) -> int:
        """Delete download_jobs past their expires_at. Returns the number of rows deleted."""
        if self.engine is None:
            return 0
        return self._run_write("DELETE FROM download_jobs WHERE expires_at < NOW()")

    def is_admin(self, email: str) -> bool:
        """Return True if the given email belongs to an admin."""
        if self.engine is None:
            return False
        rows = self._run("SELECT 1 FROM admins WHERE email = :email", {"email": email})
        return len(rows) > 0

    def is_authorized_user(self, email: str) -> bool:
        """Return True if the given email is in the authorized users list."""
        if self.engine is None:
            return False
        rows = self._run(
            "SELECT 1 FROM authorized_users WHERE email = :email", {"email": email}
        )
        return len(rows) > 0

    def add_authorized_user(self, email: str, name: str) -> bool:
        """Add a user to the authorized users list. Returns True if successful."""
        if self.engine is None:
            return False
        self._run_write(
            "INSERT INTO authorized_users (email, name) VALUES (:email, :name) "
            "ON CONFLICT DO NOTHING",
            {"email": email, "name": name}
        )
        return True

    def remove_authorized_user(self, email: str) -> bool:
        """Remove a user from the authorized users list. Returns True if deleted."""
        if self.engine is None:
            return False
        rowcount = self._run_write(
            "DELETE FROM authorized_users WHERE email = :email", {"email": email}
        )
        return rowcount > 0

    def update_authorized_user_name(self, email: str, name: str) -> bool:
        """Update the display name of an authorized user. Returns True if updated."""
        if self.engine is None:
            return False
        rowcount = self._run_write(
            "UPDATE authorized_users SET name = :name WHERE email = :email",
            {"name": name, "email": email}
        )
        return rowcount > 0

    def get_authorized_users(self) -> List[Dict[str, Any]]:
        """Return all authorized users including their last_login from the users table."""
        if self.engine is None:
            return []
        sql = """
            SELECT au.email, au.name, au.authorized_at, u.last_login
            FROM authorized_users au
            LEFT JOIN users u ON u.email = au.email
            ORDER BY au.authorized_at DESC
        """
        rows = self._run(sql)
        return [
            {
                "email": row[0],
                "name": row[1],
                "authorized_at": row[2],
                "last_login": row[3]
            }
            for row in rows
        ]

    def update_last_login(self, email: str, name: str) -> None:
        """Upsert the user row and stamp last_login to NOW()."""
        if self.engine is None:
            return
        self._run_write(
            "INSERT INTO users (email, name, last_login) VALUES (:email, :name, NOW()) "
            "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, last_login = NOW()",
            {"email": email, "name": name}
        )

    def get_last_login(self, email: str) -> Optional[Any]:
        """Return the last_login timestamp for a user, or None if not found."""
        if self.engine is None:
            return None
        rows = self._run(
            "SELECT last_login FROM users WHERE email = :email", {"email": email}
        )
        return rows[0][0] if rows else None

    def get_download_jobs(self, user_email: str) -> List[Dict[str, Any]]:
        """Return all download jobs for the given user, newest first."""
        if self.engine is None:
            return []
        sql = """
            SELECT job_id, user_email, docket_ids, format, include_binaries,
                status, s3_path, created_at, updated_at, expires_at
            FROM download_jobs
            WHERE user_email = :user_email
            ORDER BY created_at DESC
        """
        rows = self._run(sql, {"user_email": user_email})
        return [
            {
                "job_id": str(row[0]),
                "user_email": row[1],
                "docket_ids": row[2],
                "format": row[3],
                "include_binaries": row[4],
                "status": row[5],
                "s3_path": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "updated_at": row[8].isoformat() if row[8] else None,
                "expires_at": row[9].isoformat() if row[9] else None,
            }
            for row in rows
        ]

    def delete_download_job(self, job_id: str, user_email: str) -> bool:
        """Delete a download job owned by the user. Returns True if deleted."""
        if self.engine is None:
            return False
        rowcount = self._run_write(
            "DELETE FROM download_jobs WHERE job_id = :job_id AND user_email = :email",
            {"job_id": job_id, "email": user_email}
        )
        return rowcount > 0


def _get_secrets_from_aws() -> Dict[str, str]:
    if boto3 is None:
        raise ImportError("boto3 is required to use AWS Secrets Manager.")
    client = boto3.client("secretsmanager", region_name="YOUR_REGION")
    response = client.get_secret_value(SecretId="YOUR_SECRET_NAME")
    return json.loads(response["SecretString"])


def get_db() -> DBLayer:
    """
    Return a DBLayer backed by the shared SQLAlchemy engine.

    The engine is created once and reused. SQLAlchemy's pool_pre_ping
    and pool_recycle settings handle dead-connection detection and
    replacement automatically — no manual rollback or health-check needed.
    """
    if LOAD_DOTENV is not None:
        LOAD_DOTENV()
    try:
        engine = _get_engine()
        return DBLayer(engine)
    except Exception:  # pylint: disable=broad-exception-caught
        return DBLayer()


def _opensearch_use_ssl_from_env(user: str, password: str) -> bool:
    """Default to HTTPS when both user and password are set."""
    raw = (os.getenv("OPENSEARCH_USE_SSL") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if _env_flag_true("OPENSEARCH_USE_SSL"):
        return True
    return bool(not raw and user and password)


def _opensearch_client_kwargs() -> Dict[str, Any]:  # pylint: disable=too-many-statements
    """Build keyword args for OpenSearch client."""
    host = (os.getenv("OPENSEARCH_HOST") or "localhost").strip() or "localhost"
    port = _parse_opensearch_port_env("OPENSEARCH_PORT", 9200)
    user = (os.getenv("OPENSEARCH_USER") or os.getenv("OPENSEARCH_USERNAME") or "").strip()
    password = (
        os.getenv("OPENSEARCH_PASSWORD")
        or os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD")
        or ""
    ).strip()
    use_ssl = _opensearch_use_ssl_from_env(user, password)
    verify = _env_flag_true("OPENSEARCH_VERIFY_CERTS")
    host_entry: Dict[str, Any] = {"host": host, "port": port}
    if use_ssl:
        host_entry["scheme"] = "https"
    kwargs: Dict[str, Any] = {
        "hosts": [host_entry],
        "use_ssl": use_ssl,
        "verify_certs": verify if use_ssl else False,
        "ssl_show_warn": False,
    }
    if use_ssl and not verify:
        kwargs["ssl_assert_hostname"] = False
    if user and password:
        kwargs["http_auth"] = (user, password)
    return kwargs


class _AossClient:  # pylint: disable=too-few-public-methods
    """Thin requests-based client that mimics opensearchpy .search() interface."""
    def __init__(self, base_url, session):
        self.base_url = base_url.rstrip('/')
        self.session = session

    def search(self, index, body):
        url = f"{self.base_url}/{index}/_search"
        # Bumped from 30s — broad bucket aggregations on large corpora can
        # need more headroom. Gunicorn worker timeout is 120s.
        resp = self.session.post(url, json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()


_OPENSEARCH_CLIENT_SINGLETON = None  # pylint: disable=invalid-name


def get_opensearch_connection():  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    global _OPENSEARCH_CLIENT_SINGLETON  # pylint: disable=global-statement

    host = (os.getenv("OPENSEARCH_HOST") or "").strip()

    use_aws = os.getenv("USE_AWS_SECRETS", "").lower() in {"1", "true", "yes", "on"}
    if not host and use_aws and boto3 is not None:
        try:
            sm = boto3.client("secretsmanager", region_name="us-east-1")
            secret = json.loads(
                sm.get_secret_value(SecretId="mirrulations/opensearch")["SecretString"]
            )
            raw_host = secret.get("host", "").strip()
            if raw_host and not raw_host.startswith("http"):
                raw_host = "https://" + raw_host
            host = raw_host
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    if "aoss.amazonaws.com" in host:
        if _OPENSEARCH_CLIENT_SINGLETON is not None:
            return _OPENSEARCH_CLIENT_SINGLETON
        creds = boto3.Session().get_credentials()
        auth = AWS4Auth(
            refreshable_credentials=creds,
            region="us-east-1",
            service="aoss",
        )
        session = requests.Session()
        session.auth = auth
        _OPENSEARCH_CLIENT_SINGLETON = _AossClient(host, session)  # pylint: disable=invalid-name
        return _OPENSEARCH_CLIENT_SINGLETON

    if LOAD_DOTENV is not None:
        LOAD_DOTENV()
    return OpenSearch(**_opensearch_client_kwargs())
