# pylint: disable=redefined-outer-name,protected-access,duplicate-code
import uuid
from datetime import datetime, timezone
import pytest
import mirrsearch.db as db_module
from mirrsearch.db import DBLayer, _env_flag_true, _parse_positive_int_env


class _FakeResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = rowcount if rowcount is not None else len(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConnection:
    """Single connection context that records executions and returns canned rows."""
    def __init__(self, engine):
        self._engine = engine

    def execute(self, stmt, params=None):
        sql = stmt.text if hasattr(stmt, "text") else str(stmt)
        call_num = len(self._engine.calls) + 1
        self._engine.calls.append((sql, params or {}))
        rows = self._engine._rows_per_call.get(call_num, self._engine._default_rows)
        rowcount = self._engine._rowcount_per_call.get(call_num, self._engine._default_rowcount)
        return _FakeResult(rows, rowcount)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeEngine:
    """Minimal fake SQLAlchemy engine for testing."""
    def __init__(self, rows=None, rowcount=None, rows_per_call=None, rowcount_per_call=None):
        self._default_rows = rows or []
        self._default_rowcount = rowcount if rowcount is not None else len(self._default_rows)
        self._rows_per_call = rows_per_call or {}
        self._rowcount_per_call = rowcount_per_call or {}
        self.calls = []
        self.committed = False

    def connect(self):
        return _FakeConnection(self)

    def begin(self):
        conn = _FakeConnection(self)
        self.committed = True
        return conn


def _FakeConn(rows=None, rowcount=None):  # pylint: disable=invalid-name
    """Compatibility shim — returns _FakeEngine."""
    return _FakeEngine(rows=rows or [], rowcount=rowcount)


def _TrackingConn(rows_per_call=None, rowcount_per_call=None):  # pylint: disable=invalid-name
    """Compatibility shim for multi-call tracking."""
    return _FakeEngine(rows_per_call=rows_per_call or {}, rowcount_per_call=rowcount_per_call or {})


# Helper function to avoid duplicate code
def _setup_opensearch_test(monkeypatch, use_ssl=True, verify_certs=False):
    """Setup OpenSearch test with common configuration."""
    captured = {}

    def fake_opensearch(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr(db_module, "OpenSearch", fake_opensearch)
    if use_ssl:
        monkeypatch.setenv("OPENSEARCH_USE_SSL", "true")
    if verify_certs:
        monkeypatch.setenv("OPENSEARCH_VERIFY_CERTS", "true")
    return captured


# --- _env_flag_true ---

def test_env_flag_true_returns_true_for_1(monkeypatch):
    monkeypatch.setenv("TEST_FLAG", "1")
    assert _env_flag_true("TEST_FLAG") is True


def test_env_flag_true_returns_true_for_true(monkeypatch):
    monkeypatch.setenv("TEST_FLAG", "true")
    assert _env_flag_true("TEST_FLAG") is True


def test_env_flag_true_returns_false_for_false(monkeypatch):
    monkeypatch.setenv("TEST_FLAG", "false")
    assert _env_flag_true("TEST_FLAG") is False


def test_env_flag_true_returns_false_when_unset(monkeypatch):
    monkeypatch.delenv("TEST_FLAG", raising=False)
    assert _env_flag_true("TEST_FLAG") is False


# --- _parse_positive_int_env ---

def test_parse_positive_int_env_valid(monkeypatch):
    monkeypatch.setenv("MY_INT", "42")
    assert _parse_positive_int_env("MY_INT", 10) == 42


def test_parse_positive_int_env_empty_returns_default(monkeypatch):
    monkeypatch.setenv("MY_INT", "")
    assert _parse_positive_int_env("MY_INT", 99) == 99


def test_parse_positive_int_env_invalid_returns_default(monkeypatch):
    monkeypatch.setenv("MY_INT", "abc")
    assert _parse_positive_int_env("MY_INT", 99) == 99


def test_parse_positive_int_env_zero_clamps_to_1(monkeypatch):
    monkeypatch.setenv("MY_INT", "0")
    assert _parse_positive_int_env("MY_INT", 10) == 1


def test_parse_positive_int_env_negative_clamps_to_1(monkeypatch):
    monkeypatch.setenv("MY_INT", "-5")
    assert _parse_positive_int_env("MY_INT", 10) == 1


# --- _get_cfr_docket_ids ---

def test_get_cfr_docket_ids_returns_empty_when_no_conn():
    assert DBLayer()._get_cfr_docket_ids([("Title 42", "413")]) == set()


def test_get_cfr_docket_ids_returns_empty_for_empty_pairs():
    db = DBLayer(engine=_FakeConn([]))
    assert db._get_cfr_docket_ids([]) == set()


def test_get_cfr_docket_ids_queries_correct_table():
    conn = _TrackingConn(rows_per_call={1: [("DOC-001",), ("DOC-002",)]})
    db = DBLayer(engine=conn)
    result = db._get_cfr_docket_ids([("Title 42", "413")])
    sql, params = conn.calls[0]
    assert "documents" in sql
    assert "cfrparts" in sql
    assert "cp.title = :title_" in sql
    assert "cp.cfrPart = :part_" in sql
    assert params.get("title_0") == "Title 42"
    assert params.get("part_0") == "413"
    assert result == {"DOC-001", "DOC-002"}


def test_get_cfr_docket_ids_multiple_pairs():
    conn = _TrackingConn(rows_per_call={1: [("DOC-001",)]})
    db = DBLayer(engine=conn)
    db._get_cfr_docket_ids([("Title 42", "413"), ("Title 40", "80")])
    sql, params = conn.calls[0]
    assert sql.count("cp.title = :title_") == 2
    assert params.get("title_0") == "Title 42"
    assert params.get("part_0") == "413"
    assert params.get("title_1") == "Title 40"
    assert params.get("part_1") == "80"


# --- date filters in _search_dockets_postgres ---

def test_search_dockets_postgres_start_date_filter():
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("test", start_date="2025-01-01")
    assert len(db.engine.calls) > 0, "No SQL was executed"
    sql, params = db.engine.calls[0]
    assert "d.modify_date::date >= :start_date::date" in sql
    assert params.get("start_date") == "2025-01-01"


def test_search_dockets_postgres_end_date_filter():
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("test", end_date="2026-01-01")
    assert len(db.engine.calls) > 0, "No SQL was executed"
    sql, params = db.engine.calls[0]
    assert "d.modify_date::date <= :end_date::date" in sql
    assert params.get("end_date") == "2026-01-01"


def test_search_dockets_postgres_both_dates():
    db = DBLayer(engine=_FakeConn([]))
    db._search_dockets_postgres("test", start_date="2025-01-01", end_date="2026-01-01")
    assert len(db.engine.calls) > 0, "No SQL was executed"
    sql, params = db.engine.calls[0]
    assert "d.modify_date::date >= :start_date::date" in sql
    assert "d.modify_date::date <= :end_date::date" in sql
    assert params.get("start_date") == "2025-01-01"
    assert params.get("end_date") == "2026-01-01"


# --- collection methods ---

def test_get_collections_no_conn_returns_empty():
    assert DBLayer().get_collections("user@example.com") == []


def test_get_collections_returns_rows():
    rows = [(1, "My Collection", "user@example.com", ["DOC-001"])]
    db = DBLayer(engine=_FakeConn(rows))
    result = db.get_collections("user@example.com")
    assert len(result) == 1
    assert result[0]["collection_id"] == 1
    assert result[0]["name"] == "My Collection"
    assert result[0]["docket_ids"] == ["DOC-001"]


def test_get_collections_non_list_docket_ids_returns_empty_list():
    rows = [(1, "My Collection", "user@example.com", None)]
    db = DBLayer(engine=_FakeConn(rows))
    result = db.get_collections("user@example.com")
    assert result[0]["docket_ids"] == []


def test_create_collection_no_conn_returns_minus_one():
    assert DBLayer().create_collection("user@example.com", "Test") == -1


def test_create_collection_returns_new_id():
    conn = _TrackingConn(rows_per_call={2: [(42,)]})
    db = DBLayer(engine=conn)
    result = db.create_collection("user@example.com", "My Collection")
    assert result == 42
    assert conn.committed is True


def test_delete_collection_no_conn_returns_false():
    assert DBLayer().delete_collection(1, "user@example.com") is False


def test_delete_collection_returns_true_when_deleted():
    conn = _FakeEngine([], rowcount=1)
    db = DBLayer(engine=conn)
    assert db.delete_collection(1, "user@example.com") is True
    assert conn.committed is True


def test_delete_collection_returns_false_when_not_found():
    conn = _FakeEngine([], rowcount=0)
    db = DBLayer(engine=conn)
    assert db.delete_collection(99, "user@example.com") is False


def test_add_docket_to_collection_no_conn_returns_false():
    assert DBLayer().add_docket_to_collection(1, "DOC-001", "user@example.com") is False


def test_add_docket_to_collection_wrong_owner_returns_false():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(engine=conn)
    result = db.add_docket_to_collection(1, "DOC-001", "other@example.com")
    assert result is False
    assert conn.committed is False


def test_add_docket_to_collection_success():
    conn = _TrackingConn(rows_per_call={1: [(1,)], 2: []})
    db = DBLayer(engine=conn)
    result = db.add_docket_to_collection(1, "DOC-001", "user@example.com")
    assert result is True
    assert conn.committed is True
    insert_sql = conn.calls[1][0]
    assert "collection_dockets" in insert_sql


def test_remove_docket_from_collection_no_conn_returns_false():
    assert DBLayer().remove_docket_from_collection(1, "DOC-001", "user@example.com") is False


def test_remove_docket_from_collection_wrong_owner_returns_false():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(engine=conn)
    result = db.remove_docket_from_collection(1, "DOC-001", "other@example.com")
    assert result is False
    assert conn.committed is False


def test_remove_docket_from_collection_success():
    conn = _TrackingConn(rows_per_call={1: [(1,)]}, rowcount_per_call={2: 1})
    db = DBLayer(engine=conn)
    result = db.remove_docket_from_collection(1, "DOC-001", "user@example.com")
    assert result is True
    assert conn.committed is True
    delete_sql = conn.calls[1][0]
    assert "collection_dockets" in delete_sql


# --- import fallback coverage (boto3 / dotenv) ---

def test_boto3_none_branch_covered(monkeypatch):
    """_get_secrets_from_aws raises ImportError when boto3 is None — covers line 10-11."""
    monkeypatch.setattr(db_module, "boto3", None)
    with pytest.raises(ImportError):
        db_module._get_secrets_from_aws()


def test_load_dotenv_none_branch_covered(monkeypatch):
    """get_db with LOAD_DOTENV=None should not crash — covers line 15-16."""
    monkeypatch.setattr(db_module, "LOAD_DOTENV", None)
    monkeypatch.setattr(db_module, "_get_engine", lambda: _FakeEngine([]))
    result = db_module.get_db()
    assert isinstance(result, DBLayer)


# --- get_docket_document_comment_totals error fallback ---

def test_get_docket_document_comment_totals_empty_ids():
    assert not DBLayer().get_docket_document_comment_totals([])


def test_get_docket_document_comment_totals_opensearch_error_returns_empty():
    class BrokenClient:  # pylint: disable=too-few-public-methods
        def search(self, **_):
            raise RuntimeError("connection refused")

    db = DBLayer()
    result = db.get_docket_document_comment_totals(
        ["DOC-001"], opensearch_client=BrokenClient()
    )
    assert not result


# --- _opensearch_use_ssl_from_env ---

def test_opensearch_use_ssl_explicit_off(monkeypatch):
    monkeypatch.setenv("OPENSEARCH_USE_SSL", "off")
    assert db_module._opensearch_use_ssl_from_env("admin", "secret") is False


def test_opensearch_use_ssl_no_credentials_no_env(monkeypatch):
    monkeypatch.delenv("OPENSEARCH_USE_SSL", raising=False)
    assert db_module._opensearch_use_ssl_from_env("", "") is False


def test_opensearch_verify_certs_true(monkeypatch):
    captured = _setup_opensearch_test(monkeypatch, use_ssl=True, verify_certs=True)
    db_module.get_opensearch_connection()
    assert captured["verify_certs"] is True
    assert "ssl_assert_hostname" not in captured


# --- download job methods ---

def test_create_download_job_no_conn_returns_empty_string():
    assert DBLayer().create_download_job("user@example.com", ["DOC-001"]) == ""


def test_create_download_job_returns_job_id():
    fake_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(engine=conn)
    result = db.create_download_job("user@example.com", ["DOC-001", "DOC-002"])
    assert result == str(fake_uuid)
    assert conn.committed is True


def test_create_download_job_upserts_user_first():
    fake_uuid = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(engine=conn)
    db.create_download_job("user@example.com", ["DOC-001"])
    first_sql = conn.calls[0][0]
    assert "INSERT INTO users" in first_sql
    assert "ON CONFLICT" in first_sql


def test_create_download_job_inserts_correct_values():
    fake_uuid = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(engine=conn)
    db.create_download_job("user@example.com", ["DOC-001"], format="csv", include_binaries=True)
    insert_sql, params = conn.calls[1]
    assert "INSERT INTO download_jobs" in insert_sql
    assert params.get("email") == "user@example.com"
    assert params.get("docket_ids") == ["DOC-001"]
    assert params.get("format") == "csv"
    assert params.get("include_binaries") is True


def test_create_download_job_defaults():
    fake_uuid = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(engine=conn)
    db.create_download_job("user@example.com", ["DOC-001"])
    _, params = conn.calls[1]
    assert params.get("format") == "zip"
    assert params.get("include_binaries") is False


def test_get_download_job_no_conn_returns_empty_dict():
    assert not DBLayer().get_download_job("some-uuid", "user@example.com")


def test_get_download_job_not_found_returns_empty_dict():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(engine=conn)
    result = db.get_download_job("missing-uuid", "user@example.com")
    assert not result


def test_get_download_job_returns_correct_fields():
    job_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    now = datetime.now(timezone.utc)
    row = (job_id, "user@example.com", ["DOC-001"], "zip", False, "pending", None, now, now, now)
    conn = _TrackingConn(rows_per_call={1: [row]})
    db = DBLayer(engine=conn)
    result = db.get_download_job(str(job_id), "user@example.com")
    assert result["job_id"] == str(job_id)
    assert result["user_email"] == "user@example.com"
    assert result["docket_ids"] == ["DOC-001"]
    assert result["format"] == "zip"
    assert result["include_binaries"] is False
    assert result["status"] == "pending"
    assert result["s3_path"] is None


def test_get_download_job_enforces_user_ownership():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(engine=conn)
    result = db.get_download_job("some-uuid", "other@example.com")
    assert not result
    sql, params = conn.calls[0]
    assert "user_email" in sql
    assert params.get("email") == "other@example.com"


def test_update_download_job_status_no_conn_returns_false():
    assert DBLayer().update_download_job_status("some-uuid", "ready") is False


def test_update_download_job_status_returns_true_when_updated():
    conn = _FakeEngine([], rowcount=1)
    db = DBLayer(engine=conn)
    result = db.update_download_job_status("some-uuid", "ready", s3_path="s3://bucket/file.zip")
    assert result is True
    assert conn.committed is True


def test_update_download_job_status_returns_false_when_not_found():
    conn = _FakeEngine([], rowcount=0)
    db = DBLayer(engine=conn)
    result = db.update_download_job_status("missing-uuid", "ready")
    assert result is False


def test_update_download_job_status_sets_correct_params():
    conn = _TrackingConn(rows_per_call={})
    db = DBLayer(engine=conn)
    db.update_download_job_status("my-uuid", "processing", s3_path=None)
    sql, params = conn.calls[0]
    assert "UPDATE download_jobs" in sql
    assert "status" in sql
    assert params.get("status") == "processing"
    assert params.get("s3_path") is None
    assert params.get("job_id") == "my-uuid"


def test_prune_expired_download_jobs_no_conn_returns_zero():
    assert DBLayer().prune_expired_download_jobs() == 0


def test_prune_expired_download_jobs_returns_deleted_count():
    conn = _FakeEngine([], rowcount=5)
    db = DBLayer(engine=conn)
    result = db.prune_expired_download_jobs()
    assert result == 5
    assert conn.committed is True


def test_prune_expired_download_jobs_uses_correct_sql():
    conn = _TrackingConn(rows_per_call={})
    db = DBLayer(engine=conn)
    db.prune_expired_download_jobs()
    sql, _params = conn.calls[0]
    assert "DELETE FROM download_jobs" in sql
    assert "expires_at" in sql
    assert "NOW()" in sql
