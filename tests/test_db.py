"""
Tests for the database layer (db.py)

Only tests DBLayer wiring, the postgres branch, and module-level
factory functions. Dummy-data behavior tests live in test_mock.py.
"""
# pylint: disable=redefined-outer-name,protected-access, too-many-lines
from types import SimpleNamespace
# pylint: disable=redefined-outer-name,protected-access,too-many-lines,duplicate-code
from datetime import datetime
import pytest
import mirrsearch.db as db_module
from mirrsearch.db import DBLayer, cfr_part_filter_patterns, get_db


# --- DBLayer instantiation ---

def test_db_layer_creation():
    """Test that DBLayer can be instantiated"""
    db = DBLayer()
    assert db is not None
    assert isinstance(db, DBLayer)


def test_db_layer_is_frozen():
    """Test that DBLayer is a frozen dataclass (immutable)"""
    db = DBLayer()
    with pytest.raises(Exception):  # FrozenInstanceError
        db.new_attribute = "test"


def test_db_layer_no_conn_returns_empty():
    """DBLayer with no connection returns empty list from search"""
    db = DBLayer()
    assert db.search("anything") == []


def test_get_agencies_no_conn_returns_empty():
    assert DBLayer().get_agencies() == []

def test_cfr_part_filter_patterns_skips_none_and_blank_parts():
    assert cfr_part_filter_patterns([None, {"part": "  "}, "413"]) == ["413"]


def test_comment_deduplication_via_cardinality():
    """
    Cross-index comment deduplication uses OpenSearch cardinality agg.
    _extract_cardinality_counts reads unique_comments.value from each index;
    _run_text_match_queries takes the max per docket so shared comment IDs
    across indexes are not double-counted.
    """
    comment_buckets = [
        _fake_os_comment_agg_bucket("D1", "matching_comments", "SHARED-ID")
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket("D1", "matching_extracted", "SHARED-ID")
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)
    db = DBLayer()
    results = db.text_match_terms(["term"], opensearch_client=fake_client)
    assert len(results) == 1
    assert results[0]["docket_id"] == "D1"
    assert results[0]["comment_match_count"] == 1

def test_search_with_cfr_dict_applies_exact_docket_filter(monkeypatch):
    """Dict-style CFR filter keeps only dockets returned by exact title+part map."""
    rows = [
        ("DOC-001", "First", "CMS", "Rulemaking", "2024-01-01", "Title 42", "413", "http://a"),
        ("DOC-002", "Second", "EPA", "Rulemaking", "2024-01-01", "Title 40", "40", "http://b"),
    ]
    db = DBLayer(engine=_FakeConn(rows))
    monkeypatch.setattr(DBLayer, "_get_cfr_docket_ids", lambda self, _pairs: {"DOC-002"})

    results = db.search(
        "docket",
        cfr_part_param=[{"title": "42 CFR Parts 413 and 512", "part": "413"}],
    )

    assert [r["docket_id"] for r in results] == ["DOC-002"]

def test_search_with_plain_cfr_string_skips_exact_cfr_lookup(monkeypatch):
    """String-style CFR filters should not invoke exact title+part lookup."""
    db = DBLayer(engine=_FakeConn([]))

    def should_not_call(self, _pairs):
        raise AssertionError("_get_cfr_docket_ids should not run for plain string filters")

    monkeypatch.setattr(DBLayer, "_get_cfr_docket_ids", should_not_call)
    db.search("x", cfr_part_param=["413"])

def test_get_db_returns_dblayer():
    """Test the get_db factory function returns a DBLayer"""
    db = get_db()
    assert isinstance(db, DBLayer)

# --- Fake SQLAlchemy engine helpers ---

class _FakeResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = rowcount if rowcount is not None else len(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConnection:
    def __init__(self, engine):
        self._engine = engine

    def execute(self, stmt, params=None):
        sql = stmt.text if hasattr(stmt, "text") else str(stmt)
        self._engine._executed.append((sql, params or {}))
        return _FakeResult(self._engine._rows, self._engine._rowcount)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeEngine:
    """Minimal fake SQLAlchemy engine for testing."""
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self._rowcount = rowcount if rowcount is not None else 0
        self._executed = []

    def connect(self):
        return _FakeConnection(self)

    def begin(self):
        return _FakeConnection(self)

    @property
    def _last_sql(self):
        return self._executed[-1][0] if self._executed else ""

    @property
    def _last_params(self):
        return self._executed[-1][1] if self._executed else {}


def _FakeConn(rows, rowcount=None):  # pylint: disable=invalid-name
    """Compatibility shim — returns a _FakeEngine so tests read naturally."""
    return _FakeEngine(rows, rowcount)

def test_get_agencies_with_conn():
    db = DBLayer(engine=_FakeConn([("CMS",), ("EPA",)]))
    assert db.get_agencies() == ["CMS", "EPA"]

# --- _search_dockets_postgres filter tests ---

def test_search_dockets_postgres_agency_filter():
    """Agency filter adds ILIKE clause and wraps value with wildcards"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("", agency=["CMS"])
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "agency_id ILIKE :agency_" in sql
    assert params.get("query") == "%%" and params.get("agency_0") == "%CMS%"

def test_search_dockets_postgres_agency_multi_filter():
    """Multiple agencies produce OR'd ILIKE clauses"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("", agency=["CMS", "EPA"])
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert sql.count("agency_id ILIKE :agency_") == 2
    assert "%CMS%" in params.values()
    assert "%EPA%" in params.values()

def test_search_dockets_postgres_docket_type_filter():
    """Docket type filter adds exact match clause"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("", docket_type_param="Rulemaking")
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "d.docket_type = :docket_type" in sql
    assert params.get("query") == "%%" and params.get("docket_type") == "Rulemaking"

def test_search_dockets_postgres_agency_and_docket_type_filter():
    """Both filters add their clauses and params in order"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("renal", docket_type_param="Rulemaking", agency=["CMS"])
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "d.docket_type = :docket_type" in sql
    assert "agency_id ILIKE :agency_" in sql
    assert params.get("query") == "%renal%"
    assert params.get("docket_type") == "Rulemaking"
    assert params.get("agency_0") == "%CMS%"

def test_search_dockets_postgres_no_filter_no_extra_clauses():
    """Without filters, SQL has no extra AND clauses beyond docket_title"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("abc")
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "d.docket_type = :docket_type" not in sql
    assert "agency_id ILIKE :agency_" not in sql
    assert params.get("query") == "%abc%"

def test_search_dockets_postgres_cfr_filter_from_api_dict():
    """Dict CFR filter applies exact cfrPart = via EXISTS and exact FRD title+part EXISTS."""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres(
        "renal",
        cfr_part_param=[{"title": "42 CFR Parts 413 and 512", "part": "413"}],
    )
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "cp3.cfrPart = :cfr_" in sql
    assert "JOIN cfrparts cp3 ON cp3.frdocnum = d3.frdocnum" in sql
    assert "JOIN cfrparts cp2 ON cp2.frdocnum = d2.frdocnum" in sql
    assert "cp2.title = :etitle_" in sql
    assert "cp2.cfrPart = :epart_" in sql
    assert params.get("query") == "%renal%"
    assert params.get("cfr_0") == "413"
    assert params.get("etitle_0") == "42 CFR Parts 413 and 512"

def test_search_dockets_postgres_cfr_empty_dict_skips_cfr_clause():
    """Dict with empty part does not add CFR SQL (avoids bogus %%dict%% params)."""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("x", cfr_part_param=[{"title": "t", "part": ""}])
    sql, _params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "cp.cfrPart ILIKE" not in sql

def test_get_opensearch_connection_blank_port_no_crash(monkeypatch):
    """Empty OPENSEARCH_PORT in .env must not raise int('') (was HTTP 500)."""
    monkeypatch.setenv("OPENSEARCH_PORT", "")
    assert db_module.get_opensearch_connection() is not None

def test_opensearch_bucket_size_blank_env_defaults(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_MATCH_DOCKET_BUCKET_SIZE", "")
    assert db_module._opensearch_match_docket_bucket_size() == 50000

def test_opensearch_bucket_size_invalid_env_defaults(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_MATCH_DOCKET_BUCKET_SIZE", "not-a-number")
    assert db_module._opensearch_match_docket_bucket_size() == 50000


def test_opensearch_comment_id_terms_size_does_not_exist():
    """Confirm the deleted constant is truly gone — prevents accidental re-introduction."""
    assert not hasattr(db_module, "_opensearch_comment_id_terms_size"), (
        "_opensearch_comment_id_terms_size should be deleted — "
        "cardinality agg replaced the nested terms agg on commentId"
    )

def test_get_opensearch_connection_invalid_port_env_defaults(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_PORT", "not-a-port")
    assert db_module.get_opensearch_connection() is not None

def test_get_opensearch_connection_port_out_of_range_defaults(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_PORT", "70000")
    assert db_module.get_opensearch_connection() is not None

def test_search_dockets_postgres_cfr_filter_plain_string():
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("z", cfr_part_param=["413"])
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "cp3.cfrPart = :cfr_" in sql
    assert "JOIN cfrparts cp3 ON cp3.frdocnum = d3.frdocnum" in sql
    assert params.get("query") == "%z%" and params.get("cfr_0") == "413"

# --- _search_dockets_postgres tests ---

def test_search_dockets_postgres_empty_results():
    """No rows returns an empty list"""
    db = DBLayer(engine=_FakeConn([]))
    results = db._search_dockets_postgres("anything")
    assert results == []

def test_search_dockets_postgres_single_docket_single_cfr():
    """Single row returns one docket with one cfr_ref"""
    rows = [("DOC-001", "Test Docket", "CMS", "Rulemaking",
             "2024-01-01", "Title 42", "42", "http://link")]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("test")

    assert len(results) == 1
    assert results[0]["docket_id"] == "DOC-001"
    assert results[0]["docket_title"] == "Test Docket"
    assert results[0]["agency_id"] == "CMS"
    assert results[0]["docket_type"] == "Rulemaking"
    assert results[0]["modify_date"] == "2024-01-01"
    assert len(results[0]["cfr_refs"]) == 1
    assert results[0]["cfr_refs"][0]["title"] == "Title 42"
    assert results[0]["cfr_refs"][0]["cfrParts"] == {"42": "http://link"}

def test_search_dockets_postgres_multiple_cfr_parts_same_title():
    """Multiple rows for same docket+title aggregate cfrParts without duplicates"""
    rows = [
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "42", "http://link"),
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "43", "http://link"),
    ]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("test")

    assert len(results) == 1
    cfr_ref = results[0]["cfr_refs"][0]
    assert cfr_ref["title"] == "Title 42"
    assert "42" in cfr_ref["cfrParts"]
    assert "43" in cfr_ref["cfrParts"]
    assert len(cfr_ref["cfrParts"]) == 2

def test_search_dockets_postgres_multiple_titles_same_docket():
    """Multiple cfr titles for the same docket produce multiple cfr_refs"""
    rows = [
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "42", "http://link42"),
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 45", "45", "http://link45"),
    ]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("test")

    assert len(results) == 1
    titles = {ref["title"] for ref in results[0]["cfr_refs"]}
    assert titles == {"Title 42", "Title 45"}

def test_search_dockets_postgres_multiple_dockets():
    """Rows for different dockets produce separate docket entries"""
    rows = [
        ("DOC-001", "First Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "42", "http://a"),
        ("DOC-002", "Second Docket", "EPA", "Rulemaking",
         "2024-02-01", "Title 40", "40", "http://b"),
    ]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("docket")

    assert len(results) == 2
    ids = {r["docket_id"] for r in results}
    assert ids == {"DOC-001", "DOC-002"}

def test_search_dockets_postgres_none_cfr_fields_ignored():
    """Rows with None title or None cfrPart do not add entries to cfr_refs"""
    rows = [
        ("DOC-001", "Test Docket", "CMS", "Rulemaking", "2024-01-01", None, None, None),
    ]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("test")

    assert len(results) == 1
    assert results[0]["cfr_refs"] == []

def test_search_dockets_postgres_duplicate_cfr_part_not_repeated():
    """Same cfrPart appearing in multiple rows is only stored once"""
    rows = [
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "42", "http://link"),
        ("DOC-001", "Test Docket", "CMS", "Rulemaking",
         "2024-01-01", "Title 42", "42", "http://link"),
    ]
    db = DBLayer(engine=_FakeConn(rows))

    results = db._search_dockets_postgres("test")

    assert results[0]["cfr_refs"][0]["cfrParts"] == {"42": "http://link"}

def test_search_dockets_postgres_query_param_formatting():
    """Query string is wrapped with %...% wildcards in params"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("clean air")
    _, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert params.get("query") == "%clean air%"

def test_search_dockets_postgres_empty_query_uses_wildcard():
    """Empty query string results in a %% wildcard param"""
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("")
    _, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert params.get("query") == "%%"

# --- get_dockets_by_ids tests ---

def test_get_dockets_by_ids_no_conn_returns_empty():
    assert DBLayer().get_dockets_by_ids(["DOC-001"]) == []

def test_get_dockets_by_ids_empty_ids_returns_empty():
    db = DBLayer(engine=_FakeConn([]))
    assert db.get_dockets_by_ids([]) == []

def test_get_dockets_by_ids_uses_any_and_reuses_row_shape():
    rows = [("DOC-002", "Other", "EPA", "Rulemaking",
             "2024-02-01", "Title 40", "40", "http://b")]
    db = DBLayer(engine=_FakeConn(rows))
    results = db.get_dockets_by_ids(["DOC-002"])
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "d.docket_id = ANY(:docket_ids)" in sql
    assert params.get("docket_ids") == ["DOC-002"]
    assert len(results) == 1
    assert results[0]["docket_id"] == "DOC-002"
    assert results[0]["docket_title"] == "Other"


# --- Factory function tests ---

def test_get_engine_uses_env_and_dotenv(monkeypatch):
    called = {"dotenv": False}

    def fake_load():
        called["dotenv"] = True

    captured = {}

    def fake_build(dsn):
        captured["dsn"] = dsn
        return _FakeEngine([])

    monkeypatch.setattr(db_module, "LOAD_DOTENV", fake_load)
    monkeypatch.setattr(db_module, "_build_engine", fake_build)
    monkeypatch.setattr(db_module, "_ENGINE", None)
    monkeypatch.setenv("DB_HOST", "dbhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "dbname")
    monkeypatch.setenv("DB_USER", "dbuser")
    monkeypatch.setenv("DB_PASSWORD", "dbpass")

    db = get_db()

    assert isinstance(db, DBLayer)
    assert called["dotenv"] is True
    assert "dbhost" in captured["dsn"]
    assert "5433" in captured["dsn"]
    assert "dbname" in captured["dsn"]


def test_get_postgres_connection_uses_aws_secrets(monkeypatch):  # pylint: disable=too-many-locals
    """USE_AWS_SECRETS=true uses boto3 to get credentials"""
    fake_creds = {
        "host": "aws-host",
        "port": "5432",
        "db": "aws-db",
        "username": "aws-user",
        "password": "aws-pass",
    }

    class FakeClient:  # pylint: disable=too-few-public-methods
        def get_secret_value(self, **_kwargs):  # pylint: disable=unused-argument
            return {"SecretString": __import__("json").dumps(fake_creds)}

        def describe_secret(self, **_kwargs):  # pylint: disable=unused-argument
            return {}

    fake_boto3 = type("boto3", (), {"client": staticmethod(lambda *a, **kw: FakeClient())})()
    captured_dsn = {}

    def fake_build(dsn):
        captured_dsn["dsn"] = dsn
        return _FakeEngine([])

    monkeypatch.setattr(db_module, "boto3", fake_boto3)
    monkeypatch.setattr(db_module, "_build_engine", fake_build)
    monkeypatch.setattr(db_module, "_ENGINE", None)
    monkeypatch.setenv("USE_AWS_SECRETS", "true")

    db = get_db()

    assert isinstance(db, DBLayer)
    assert "aws-host" in captured_dsn["dsn"]
    assert "aws-db" in captured_dsn["dsn"]

def test_get_secrets_from_aws_raises_without_boto3(monkeypatch):
    """_get_secrets_from_aws raises ImportError when boto3 is None"""
    monkeypatch.setattr(db_module, "boto3", None)
    with pytest.raises(ImportError):
        db_module._get_secrets_from_aws()


def test_get_db_uses_postgres_when_env_set(monkeypatch):
    sentinel = DBLayer(engine="conn")
    monkeypatch.setattr(db_module, "_get_engine", lambda: sentinel.engine)

    db = get_db()

    assert isinstance(db, DBLayer)


def test_get_opensearch_connection(monkeypatch):
    captured = {}

    def fake_opensearch(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(db_module, "OpenSearch", fake_opensearch)

    client = db_module.get_opensearch_connection()

    assert client == "client"
    assert captured["hosts"] == [{"host": "localhost", "port": 9200}]
    assert captured["use_ssl"] is False
    assert captured["verify_certs"] is False
    assert "http_auth" not in captured


def test_get_opensearch_connection_https_and_basic_auth(monkeypatch):
    captured = {}

    def fake_opensearch(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(db_module, "OpenSearch", fake_opensearch)
    monkeypatch.setenv("OPENSEARCH_USE_SSL", "true")
    monkeypatch.setenv("OPENSEARCH_USER", "admin")
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "secret")

    client = db_module.get_opensearch_connection()

    assert client == "client"
    assert captured["use_ssl"] is True
    assert captured["verify_certs"] is False
    assert captured["http_auth"] == ("admin", "secret")
    assert captured["hosts"] == [
        {"host": "localhost", "port": 9200, "scheme": "https"},
    ]
    assert captured.get("ssl_assert_hostname") is False

def test_get_opensearch_connection_ssl_implicit_when_credentials_only(monkeypatch):
    """EC2-style .env: user+password but no OPENSEARCH_USE_SSL → HTTPS."""
    captured = {}

    def fake_opensearch(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(db_module, "OpenSearch", fake_opensearch)
    monkeypatch.delenv("OPENSEARCH_USE_SSL", raising=False)
    monkeypatch.setenv("OPENSEARCH_USER", "admin")
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "x")

    db_module.get_opensearch_connection()

    assert captured["use_ssl"] is True
    assert captured["hosts"][0].get("scheme") == "https"

def test_get_opensearch_connection_ssl_explicit_off_with_auth(monkeypatch):
    captured = {}

    def fake_opensearch(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(db_module, "OpenSearch", fake_opensearch)
    monkeypatch.setenv("OPENSEARCH_USE_SSL", "false")
    monkeypatch.setenv("OPENSEARCH_USER", "admin")
    monkeypatch.setenv("OPENSEARCH_PASSWORD", "x")

    db_module.get_opensearch_connection()

    assert captured["use_ssl"] is False
    assert "scheme" not in captured["hosts"][0]

# --- OpenSearch text_match_terms tests ---

def _fake_os_comment_agg_bucket(docket_key: str, agg_name: str, *comment_ids: str) -> dict:
    """
    Build a by_docket bucket matching the new cardinality agg shape.
    unique_comments.value = count of distinct comment IDs (mirrors cardinality response).
    doc_count reflects how many documents matched the filter.
    """
    unique_count = len(set(comment_ids))
    return {
        "key": docket_key,
        agg_name: {
            "doc_count": unique_count,
            "unique_comments": {"value": unique_count},
        },
    }


class _FakeOpenSearch: #pylint: disable=too-few-public-methods
    """
    Fake OpenSearch client returning cardinality-style agg responses.
    Comment counts come from unique_comments.value, not by_comment buckets.
    """
    def __init__(self, doc_buckets, comment_buckets, extracted_buckets):
        self.doc_buckets = doc_buckets
        self.comment_buckets = comment_buckets
        self.extracted_buckets = extracted_buckets
        self.searches = []

    def search(self, index, body):
        self.searches.append((index, body))
        if index == "documents_text":
            return {"aggregations": {"by_docket": {"buckets": self.doc_buckets}}}
        if index == "comments":
            return {"aggregations": {"by_docket": {"buckets": self.comment_buckets}}}
        if index == "comments_extracted_text":
            return {"aggregations": {"by_docket": {"buckets": self.extracted_buckets}}}
        return {"aggregations": {"by_docket": {"buckets": []}}}

def test_text_match_terms_searches_comments_and_extracted():
    """
    text_match_terms searches all three indexes and returns correct comment count
    from OpenSearch cardinality (max of both comment indexes).
    """
    comment_buckets = [
        _fake_os_comment_agg_bucket(
            "CMS-2025-0240", "matching_comments", "c1", "c2")
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket(
            "CMS-2025-0240", "matching_extracted", "e1", "e2", "e3", "e4")
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)

    db = DBLayer()

    results = db.text_match_terms(["medicare"], opensearch_client=fake_client)

    assert len(fake_client.searches) == 3
    assert fake_client.searches[0][0] == "documents_text"
    assert fake_client.searches[1][0] == "comments"
    assert fake_client.searches[2][0] == "comments_extracted_text"

    assert len(results) == 1
    assert results[0]["docket_id"] == "CMS-2025-0240"
    assert results[0]["comment_match_count"] == 4
    assert results[0]["document_match_count"] == 0


def test_text_match_terms_combines_comment_sources():
    """Comment body and extracted text both contribute dockets; cardinality takes the max."""
    comment_buckets = [
        _fake_os_comment_agg_bucket("DEA-2024-0059", "matching_comments", "c1")
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket("DEA-2024-0059", "matching_extracted", "e1")
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)

    db = DBLayer()

    results = db.text_match_terms(["cannabis"], opensearch_client=fake_client)

    assert len(results) == 1
    assert results[0]["docket_id"] == "DEA-2024-0059"
    assert results[0]["comment_match_count"] == 1
    assert results[0]["document_match_count"] == 0


def test_text_match_terms_same_comment_id_body_and_extracted_counts_once():
    """
    Same commentId in both indexes is counted once.
    Cardinality agg handles deduplication — max(1, 1) = 1, not 2.
    """
    comment_buckets = [
        _fake_os_comment_agg_bucket("D1", "matching_comments", "SHARED-COMMENT-ID")
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket("D1", "matching_extracted", "SHARED-COMMENT-ID")
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)

    db = DBLayer()

    results = db.text_match_terms(["x"], opensearch_client=fake_client)

    assert len(results) == 1
    assert results[0]["docket_id"] == "D1"
    assert results[0]["comment_match_count"] == 1
    assert results[0]["document_match_count"] == 0


def test_text_match_terms_multiple_dockets_comments():
    """Multiple dockets each get their own cardinality-based comment count."""
    comment_buckets = [
        _fake_os_comment_agg_bucket("CMS-2025-0240", "matching_comments", "c1", "c2"),
        _fake_os_comment_agg_bucket("DEA-2024-0059", "matching_comments", "c3"),
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket(
            "CMS-2025-0240", "matching_extracted", "e1", "e2", "e3", "e4")
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)

    db = DBLayer()

    results = db.text_match_terms(["test"], opensearch_client=fake_client)

    assert len(results) == 2
    cms = next(r for r in results if r["docket_id"] == "CMS-2025-0240")
    assert cms["comment_match_count"] == 4
    assert cms["document_match_count"] == 0

    dea = next(r for r in results if r["docket_id"] == "DEA-2024-0059")
    assert dea["comment_match_count"] == 1
    assert dea["document_match_count"] == 0

def test_text_match_terms_uses_filtered_aggregations():
    """
    Verify the OpenSearch queries use cardinality agg (not by_comment terms agg).
    """
    fake_client = _FakeOpenSearch([], [], [])
    db = DBLayer()

    db.text_match_terms(["medicare", "medicaid"], opensearch_client=fake_client)

    assert len(fake_client.searches) == 3

    comment_index, comment_body = fake_client.searches[1]
    assert comment_index == "comments"
    assert comment_body["size"] == 0
    assert "aggs" in \
        comment_body
    assert "matching_comments" in \
        comment_body["aggs"]["by_docket"]["aggs"]
    assert "filter" in \
        comment_body["aggs"]["by_docket"]["aggs"]["matching_comments"]
    assert "unique_comments" in \
        comment_body["aggs"]["by_docket"]["aggs"]["matching_comments"]["aggs"]
    assert "cardinality" in \
        comment_body["aggs"]["by_docket"]["aggs"]["matching_comments"]["aggs"]["unique_comments"]
    assert "by_comment" not in \
        comment_body["aggs"]["by_docket"]["aggs"]["matching_comments"].get("aggs", {})

    extracted_index, extracted_body = fake_client.searches[2]
    assert extracted_index == "comments_extracted_text"
    assert "matching_extracted" in \
        extracted_body["aggs"]["by_docket"]["aggs"]
    assert "unique_comments" in \
        extracted_body["aggs"]["by_docket"]["aggs"]["matching_extracted"]["aggs"]
    assert "by_comment" not in \
        extracted_body["aggs"]["by_docket"]["aggs"]["matching_extracted"].get("aggs", {})

def test_text_match_terms_returns_correct_structure():
    """Verify each result has the required fields with correct types."""
    comment_buckets = [
        _fake_os_comment_agg_bucket("TEST-001", "matching_comments", *[f"C{i}" for i in range(5)])
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, [])

    db = DBLayer()

    results = db.text_match_terms(["test"], opensearch_client=fake_client)

    assert len(results) == 1
    assert "docket_id" in results[0]
    assert "document_match_count" in results[0]
    assert "comment_match_count" in results[0]
    assert isinstance(results[0]["docket_id"], str)
    assert isinstance(results[0]["document_match_count"], int)
    assert isinstance(results[0]["comment_match_count"], int)

def test_text_match_terms_handles_empty_results():
    """When OpenSearch returns no buckets, return empty list."""
    fake_client = _FakeOpenSearch([], [], [])
    db = DBLayer()

    results = db.text_match_terms(["nonexistent"], opensearch_client=fake_client)

    assert not results

def test_text_match_terms_only_returns_comment_matches():
    """Only dockets with doc_count > 0 in the filter agg are included."""
    comment_buckets = [
        _fake_os_comment_agg_bucket("HAS-MATCH", "matching_comments", "H1", "H2", "H3", "H4", "H5"),
        {
            "key": "NO-MATCH",
            "matching_comments": {"doc_count": 0, "unique_comments": {"value": 0}},
        },
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, [])

    db = DBLayer()

    results = db.text_match_terms(["test"], opensearch_client=fake_client)

    assert len(results) == 1
    assert results[0]["docket_id"] == "HAS-MATCH"

def test_text_match_terms_docket_only_in_comments():
    """Docket with matches only in comment body text is included with correct count."""
    comment_buckets = [
        _fake_os_comment_agg_bucket(
            "COMMENT-ONLY", "matching_comments", *[f"C{i}" for i in range(10)])
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, [])

    db = DBLayer()

    results = db.text_match_terms(["test"], opensearch_client=fake_client)

    assert len(results) == 1
    assert results[0]["docket_id"] == "COMMENT-ONLY"
    assert results[0]["comment_match_count"] == 10

def test_text_match_terms_malformed_response_returns_empty():
    class BadClient:  # pylint: disable=too-few-public-methods
        def search(self, index, body):  # pylint: disable=unused-argument
            return {}

    db = DBLayer()
    assert db.text_match_terms(["x"], opensearch_client=BadClient()) == []


# --- is_admin tests ---

def test_is_admin_no_conn_returns_false():
    assert DBLayer().is_admin("professor@email.com") is False

def test_is_admin_returns_true_when_found():
    db = DBLayer(engine=_FakeConn([(1,)]))
    assert db.is_admin("professor@email.com") is True

def test_is_admin_returns_false_when_not_found():
    db = DBLayer(engine=_FakeConn([]))
    assert db.is_admin("notadmin@email.com") is False


# --- is_authorized_user tests ---

def test_is_authorized_user_no_conn_returns_false():
    assert DBLayer().is_authorized_user("user@email.com") is False

def test_is_authorized_user_returns_true_when_found():
    db = DBLayer(engine=_FakeConn([(1,)]))
    assert db.is_authorized_user("user@email.com") is True

def test_is_authorized_user_returns_false_when_not_found():
    db = DBLayer(engine=_FakeConn([]))
    assert db.is_authorized_user("unknown@email.com") is False


# --- add_authorized_user tests ---

def test_add_authorized_user_no_conn_returns_false():
    assert DBLayer().add_authorized_user("user@email.com", "Test User") is False

def test_add_authorized_user_inserts_and_returns_true():
    db = DBLayer(engine=_FakeConn([]))
    result = db.add_authorized_user("user@email.com", "Test User")
    assert result is True
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "INSERT INTO authorized_users" in sql
    assert params.get("email") == "user@email.com" and params.get("name") == "Test User"

# --- remove_authorized_user tests ---

def test_remove_authorized_user_no_conn_returns_false():
    assert DBLayer().remove_authorized_user("user@email.com") is False

def test_remove_authorized_user_returns_true_when_deleted():
    db = DBLayer(engine=_FakeConn([]))
    db = DBLayer(engine=_FakeEngine([], rowcount=1))
    assert db.remove_authorized_user("user@email.com") is True

def test_remove_authorized_user_returns_false_when_not_found():
    db = DBLayer(engine=_FakeConn([]))
    db = DBLayer(engine=_FakeEngine([], rowcount=0))
    assert db.remove_authorized_user("nobody@email.com") is False


# --- get_authorized_users tests ---

def test_get_authorized_users_no_conn_returns_empty():
    assert DBLayer().get_authorized_users() == []

def test_get_authorized_users_returns_list():
    rows = [
        ("user1@email.com", "User One", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        ("user2@email.com", "User Two", "2026-01-02T00:00:00", "2026-01-02T00:00:00"),
    ]
    db = DBLayer(engine=_FakeConn(rows))
    results = db.get_authorized_users()
    assert len(results) == 2
    assert results[0]["email"] == "user1@email.com"
    assert results[0]["name"] == "User One"
    assert results[0]["authorized_at"] == "2026-01-01T00:00:00"
    assert results[1]["email"] == "user2@email.com"

def test_get_authorized_users_empty_table_returns_empty():
    db = DBLayer(engine=_FakeConn([]))
    assert db.get_authorized_users() == []

def test_get_expired_download_jobs_no_conn():
    assert DBLayer().get_expired_download_jobs() == []


def test_get_expired_download_jobs_returns_list():
    rows = [("job-1", "s3://bucket/downloads/job-1.zip")]
    db = DBLayer(engine=_FakeConn(rows))
    result = db.get_expired_download_jobs()
    assert len(result) == 1
    assert result[0]["job_id"] == "job-1"
    assert result[0]["s3_path"] == "s3://bucket/downloads/job-1.zip"


def test_get_expired_download_jobs_empty():
    db = DBLayer(engine=_FakeConn([]))
    assert db.get_expired_download_jobs() == []


def test_get_download_s3_url_no_conn():
    assert DBLayer().get_download_s3_url("job-1", "user@test.com") is None


def test_get_download_s3_url_no_job():
    db = DBLayer(engine=_FakeConn([]))
    assert db.get_download_s3_url("nonexistent", "user@test.com") is None


def test_get_download_s3_url_local_path():
    rows = [("job-1", "user@test.com", ["CMS-2025-0240"], "raw",
             False, "ready", "local:///tmp/job-1.zip", None, None, None)]
    db = DBLayer(engine=_FakeConn(rows))
    result = db.get_download_s3_url("job-1", "user@test.com")
    assert result == "/tmp/job-1.zip"


def test_presign_s3_url_invalid_path():
    db = DBLayer()
    assert db._presign_s3_url("not-an-s3-path") is None


def test_presign_s3_url_missing_key():
    db = DBLayer()
    assert db._presign_s3_url("s3://bucket-only") is None


# --- update_last_login tests ---

def test_update_last_login_no_conn_returns_none():
    assert DBLayer().update_last_login("user@email.com", "Test User") is None

def test_update_last_login_executes_upsert():
    db = DBLayer(engine=_FakeConn([]))
    db.update_last_login("user@email.com", "Test User")
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "INSERT INTO users" in sql
    assert "ON CONFLICT (email) DO UPDATE" in sql
    assert "last_login" in sql
    assert params.get("email") == "user@email.com" and params.get("name") == "Test User"

def test_update_last_login_commits():
    db = DBLayer(engine=_FakeConn([]))
    db.update_last_login("user@email.com", "Test User")
    assert len(db.engine._executed) == 1

def test_update_last_login_sets_name_in_params():
    db = DBLayer(engine=_FakeConn([]))
    db.update_last_login("prof@moravian.edu", "Dr. Smith")
    _, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert params.get("email") == "prof@moravian.edu"
    assert params.get("name") == "Dr. Smith"

def test_update_authorized_user_name_no_conn_returns_false():
    assert DBLayer().update_authorized_user_name("user@email.com", "New Name") is False

def test_update_authorized_user_name_updates_and_returns_true():
    db = DBLayer(engine=_FakeConn([]))
    db = DBLayer(engine=_FakeEngine([], rowcount=1))
    result = db.update_authorized_user_name("user@email.com", "New Name")
    assert result is True
    sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "UPDATE authorized_users" in sql
    assert "SET name = :name" in sql
    assert params.get("name") == "New Name" and params.get("email") == "user@email.com"

def test_update_authorized_user_name_returns_false_when_not_found():
    db = DBLayer(engine=_FakeConn([]))
    db = DBLayer(engine=_FakeEngine([], rowcount=0))
    assert db.update_authorized_user_name("nobody@email.com", "Name") is False

# --- get_download_jobs tests ---

# --- Additional coverage tests for missing lines ---

# Lines 362-368: _build_docket_agg_query_unique_comments cardinality structure
def test_build_docket_agg_query_unique_comments_has_cardinality():
    """Verify cardinality agg structure is correct in unique comments query."""
    body = DBLayer._build_docket_agg_query_unique_comments(
        "matching_comments",
        [{"match": {"commentText": "medicare"}}]
    )
    agg = body["aggs"]["by_docket"]["aggs"]["matching_comments"]["aggs"]
    assert "unique_comments" in agg
    assert "cardinality" in agg["unique_comments"]
    assert agg["unique_comments"]["cardinality"]["field"] == "commentId.keyword"
    assert agg["unique_comments"]["cardinality"]["precision_threshold"] == 3000


# Line 383: _accumulate_counts match_count > 0 branch
def test_accumulate_counts_skips_zero_match_buckets():
    """Buckets with doc_count 0 are not added to docket_counts."""
    docket_counts = {}
    buckets = [
        {"key": "D1", "matching_docs": {"doc_count": 5}},
        {"key": "D2", "matching_docs": {"doc_count": 0}},
    ]
    DBLayer._accumulate_counts(docket_counts, buckets, "matching_docs", "document_match_count")
    assert "D1" in docket_counts
    assert docket_counts["D1"]["document_match_count"] == 5
    assert "D2" not in docket_counts


# Lines 389-391: _accumulate_counts accumulates across multiple buckets
def test_accumulate_counts_accumulates_multiple_buckets():
    """Multiple matching buckets accumulate into docket_counts correctly."""
    docket_counts = {}
    buckets = [
        {"key": "D1", "matching_docs": {"doc_count": 3}},
        {"key": "D2", "matching_docs": {"doc_count": 7}},
    ]
    DBLayer._accumulate_counts(docket_counts, buckets, "matching_docs", "document_match_count")
    assert docket_counts["D1"]["document_match_count"] == 3
    assert docket_counts["D2"]["document_match_count"] == 7


def test_get_download_jobs_returns_all_jobs():
    from datetime import timezone  # pylint: disable=import-outside-toplevel
    utc = timezone.utc
    rows = [
        (
            "job-uuid-1", "user@email.com", ["CMS-2025-0240"], "raw", False, "pending", None,
            datetime(2025, 1, 1, tzinfo=utc), datetime(2025, 1, 1, tzinfo=utc),
            datetime(2025, 1, 8, tzinfo=utc)
        ),
        (
            "job-uuid-2", "user@email.com", ["CMS-2025-0241"], "csv", True, "ready",
            "s3://bucket/job-uuid-2.zip",
            datetime(2025, 1, 2, tzinfo=utc), datetime(2025, 1, 2, tzinfo=utc),
            datetime(2025, 1, 9, tzinfo=utc)
        ),
    ]

    class _FakeResult:  # pylint: disable=too-few-public-methods
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class _FakeConn:  # pylint: disable=too-few-public-methods
        def __init__(self, rows):
            self.rows = rows

        def connect(self):
            outer = self

            class _Ctx:
                def execute(self, sql, params=None):  # pylint: disable=unused-argument
                    return _FakeResult(outer.rows)

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

            return _Ctx()

    db = DBLayer(engine=_FakeConn(rows))
    results = db.get_download_jobs("user@email.com")
    assert len(results) == 2
    assert results[0]["job_id"] == "job-uuid-1"
    assert results[0]["user_email"] == "user@email.com"
    assert results[0]["docket_ids"] == ["CMS-2025-0240"]
    assert results[0]["format"] == "raw"
    assert results[0]["include_binaries"] is False
    assert results[0]["status"] == "pending"
    assert results[0]["s3_path"] is None
    assert results[1]["job_id"] == "job-uuid-2"
    assert results[1]["status"] == "ready"
    assert results[1]["s3_path"] == "s3://bucket/job-uuid-2.zip"

def test_get_download_jobs_empty_table_returns_empty():
    db = DBLayer(engine=_FakeConn([]))
    assert db.get_download_jobs("user@email.com") == []


# Lines 400-402: text_match_terms KeyError/AttributeError fallback
def test_text_match_terms_keyerror_returns_empty():
    """KeyError in _run_text_match_queries returns empty list."""
    class KeyErrorClient: #pylint: disable=too-few-public-methods
        def search(self, index, body):
            raise KeyError("aggregations")
    db = DBLayer()
    assert db.text_match_terms(["x"], opensearch_client=KeyErrorClient()) == []


def test_text_match_terms_exception_returns_empty():
    """Generic exception in _run_text_match_queries returns empty list."""
    class BrokenClient: #pylint: disable=too-few-public-methods
        def search(self, index, body):
            raise RuntimeError("connection refused")
    db = DBLayer()
    assert db.text_match_terms(["x"], opensearch_client=BrokenClient()) == []


# Lines 465-472: _run_text_match_queries document match accumulation
def test_run_text_match_queries_document_counts():
    """Document match counts from documents_text are accumulated correctly."""
    doc_buckets = [
        {"key": "DOC-001", "matching_docs": {"doc_count": 4}},
        {"key": "DOC-002", "matching_docs": {"doc_count": 2}},
    ]
    fake_client = _FakeOpenSearch(doc_buckets, [], [])
    db = DBLayer()
    results = db.text_match_terms(["test"], opensearch_client=fake_client)
    ids = {r["docket_id"]: r for r in results}
    assert ids["DOC-001"]["document_match_count"] == 4
    assert ids["DOC-002"]["document_match_count"] == 2


# Lines 485-498: _collect_matched_dockets and matched_comment_dockets set union
def test_collect_matched_dockets_unions_both_indexes():
    """Dockets from both comments and extracted indexes are unioned correctly."""
    comment_buckets = [
        _fake_os_comment_agg_bucket("D1", "matching_comments", "c1"),
    ]
    extracted_buckets = [
        _fake_os_comment_agg_bucket("D2", "matching_extracted", "e1"),
    ]
    fake_client = _FakeOpenSearch([], comment_buckets, extracted_buckets)
    db = DBLayer()
    results = db.text_match_terms(["x"], opensearch_client=fake_client)
    docket_ids = {r["docket_id"] for r in results}
    assert "D1" in docket_ids
    assert "D2" in docket_ids


# Line 503: _run_text_match_queries setdefault for existing docket in comment_counts
def test_run_text_match_queries_comment_count_set_on_existing_docket():
    """Comment count is set on a docket that already has a document match count."""
    doc_buckets = [
        {"key": "BOTH-001", "matching_docs": {"doc_count": 3}},
    ]
    comment_buckets = [
        _fake_os_comment_agg_bucket("BOTH-001", "matching_comments", "c1", "c2"),
    ]
    fake_client = _FakeOpenSearch(doc_buckets, comment_buckets, [])
    db = DBLayer()
    results = db.text_match_terms(["test"], opensearch_client=fake_client)
    assert len(results) == 1
    assert results[0]["document_match_count"] == 3
    assert results[0]["comment_match_count"] == 2


# Lines 537-539: _comment_total_query static method
def test_comment_total_query_structure():
    """_comment_total_query returns correct OpenSearch query structure."""
    query = DBLayer._comment_total_query(["D1", "D2"])
    assert query["size"] == 0
    assert "query" in query
    assert "aggs" in query
    assert "by_docket" in query["aggs"]
    assert query["aggs"]["by_docket"]["terms"]["size"] == 2


# Lines 550-576: get_docket_document_comment_totals and _fetch_docket_totals
def test_get_docket_document_comment_totals_empty_returns_empty():
    """Empty docket_ids returns empty dict without hitting DB."""
    db = DBLayer(engine=_FakeConn([]))
    assert not db.get_docket_document_comment_totals([])


def test_get_docket_document_comment_totals_no_conn_returns_empty():
    """No connection returns empty dict."""
    db = DBLayer()
    assert not db.get_docket_document_comment_totals(["D1"])


def test_fetch_docket_totals_returns_document_and_comment_counts():
    """_fetch_docket_totals returns both document and comment counts from Postgres."""
    call_count = [0]

    class _FakeResult:  # pylint: disable=too-few-public-methods
        def __init__(self, rows):
            self.rows = rows
        def fetchall(self):
            return self.rows

    class _FakeConn:  # pylint: disable=too-few-public-methods
        def execute(self, sql, params=None):  # pylint: disable=unused-argument
            call_count[0] += 1
            if call_count[0] == 1:
                return _FakeResult([("D1", 5)])
            return _FakeResult([("D1", 12)])

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class _FakeEngine:  # pylint: disable=too-few-public-methods
        def connect(self):
            return _FakeConn()

    db = DBLayer(engine=_FakeEngine())
    result = db._fetch_docket_totals(["D1"])
    assert result["D1"]["document_total_count"] == 5
    assert result["D1"]["comment_total_count"] == 12


def test_fetch_docket_totals_exception_returns_empty():
    """Exception in _fetch_docket_totals is caught and returns empty dict."""
    class _BrokenConn:
        def cursor(self):
            raise RuntimeError("DB down")
        def commit(self):
            pass

    db = DBLayer(engine=_BrokenConn())
    result = db.get_docket_document_comment_totals(["D1"])
    assert not result


# --- _AossClient init and search ---
def test_aoss_client_search_calls_correct_url():
    """_AossClient.search constructs correct URL and returns JSON."""

    class _FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"aggregations": {}}

    class _FakeSession: # pylint: disable=too-few-public-methods
        def __init__(self):
            self.calls = []
        def post(self, url, json=None, timeout=None): # pylint: disable=unused-argument
            self.calls.append(url)
            return _FakeResponse()

    session = _FakeSession()
    client = db_module._AossClient("https://example.aoss.amazonaws.com", session)
    result = client.search(index="comments", body={"size": 0})
    assert "https://example.aoss.amazonaws.com/comments/_search" in session.calls
    assert result == {"aggregations": {}}


# --- get_opensearch_connection AWS secrets path ---
def test_get_opensearch_connection_aoss_host_uses_singleton(monkeypatch):
    """AOSS host returns singleton _AossClient and reuses it on second call."""

    monkeypatch.setattr(db_module, "_OPENSEARCH_CLIENT_SINGLETON", None)
    monkeypatch.setenv("OPENSEARCH_HOST", "https://test.aoss.amazonaws.com")

    mocks = SimpleNamespace(
        boto3=SimpleNamespace(
            Session=lambda: SimpleNamespace(get_credentials=lambda: object())  # pylint: disable=unnecessary-lambda
        ),
        AWS4Auth=lambda **_: SimpleNamespace(),
        requests=SimpleNamespace(
            Session=lambda: SimpleNamespace(auth=None)
        ),
    )

    monkeypatch.setattr(db_module, "boto3", mocks.boto3)
    monkeypatch.setattr(db_module, "AWS4Auth", mocks.AWS4Auth)
    monkeypatch.setattr(db_module, "requests", mocks.requests)

    client1 = db_module.get_opensearch_connection()
    assert isinstance(client1, db_module._AossClient)

    client2 = db_module.get_opensearch_connection()
    assert client1 is client2

    monkeypatch.setattr(db_module, "_OPENSEARCH_CLIENT_SINGLETON", None)

def test_get_download_jobs_queries_correct_user():
    """Only jobs matching the given user_email are fetched."""
    db = DBLayer(engine=_FakeConn([]))
    db.get_download_jobs("specific@email.com")
    _sql, params = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert params.get("user_email") == "specific@email.com"

def test_get_download_jobs_orders_by_created_at_desc():
    """SQL should order results newest first."""
    db = DBLayer(engine=_FakeConn([]))
    db.get_download_jobs("user@email.com")
    sql, _ = (db.engine._executed[0][0], db.engine._executed[0][1])
    assert "ORDER BY created_at DESC" in sql
