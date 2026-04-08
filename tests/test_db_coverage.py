# pylint: disable=redefined-outer-name,protected-access
import uuid
from datetime import datetime, timezone
import pytest
import mirrsearch.db as db_module
from mirrsearch.db import DBLayer, _env_flag_true, _parse_positive_int_env


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []  # Store tuples of (sql, params) for each execution
        self.rowcount = len(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows=None, fetchone_rows=None):
        self._rows = rows or []
        self._fetchone_rows = fetchone_rows
        self.cursor_obj = _FakeCursor(rows)
        self.committed = False

    def cursor(self):
        # Return the same cursor object each time to maintain state
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        pass


class _TrackingConn:
    """Conn that records all cursor executions across multiple cursor() calls."""
    def __init__(self, rows_per_call=None):
        self.calls = []
        self._rows_per_call = rows_per_call or {}
        self.committed = False

    def cursor(self):
        return _TrackingCursor(self)

    def commit(self):
        self.committed = True


class _TrackingCursor:
    def __init__(self, conn):
        self._conn = conn
        self._sql = None
        self._params = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self._sql = sql
        self._params = params
        self._conn.calls.append((sql, params))

    def fetchall(self):
        return self._conn._rows_per_call.get(len(self._conn.calls), [])

    def fetchone(self):
        rows = self._conn._rows_per_call.get(len(self._conn.calls), [])
        return rows[0] if rows else None

    def close(self):
        pass


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
    db = DBLayer(conn=_FakeConn([]))
    assert db._get_cfr_docket_ids([]) == set()


def test_get_cfr_docket_ids_queries_correct_table():
    conn = _TrackingConn(rows_per_call={1: [("DOC-001",), ("DOC-002",)]})
    db = DBLayer(conn=conn)
    result = db._get_cfr_docket_ids([("Title 42", "413")])
    sql, params = conn.calls[0]
    assert "documentsWithFRdoc" in sql
    assert "cfrparts" in sql
    assert "cp.title = %s" in sql
    assert "cp.cfrPart = %s" in sql
    assert "Title 42" in params
    assert "413" in params
    assert result == {"DOC-001", "DOC-002"}


def test_get_cfr_docket_ids_multiple_pairs():
    conn = _TrackingConn(rows_per_call={1: [("DOC-001",)]})
    db = DBLayer(conn=conn)
    db._get_cfr_docket_ids([("Title 42", "413"), ("Title 40", "80")])
    sql, params = conn.calls[0]
    assert sql.count("cp.title = %s") == 2
    assert "Title 42" in params
    assert "413" in params
    assert "Title 40" in params
    assert "80" in params


# --- date filters in _search_dockets_postgres ---

def test_search_dockets_postgres_start_date_filter():
    db = DBLayer(conn=_FakeConn([]))
    db._search_dockets_postgres("test", start_date="2025-01-01")
    assert len(db.conn.cursor_obj.executed) > 0, "No SQL was executed"
    sql, params = db.conn.cursor_obj.executed[0]
    assert "d.modify_date::date >= %s::date" in sql
    assert "2025-01-01" in params


def test_search_dockets_postgres_end_date_filter():
    db = DBLayer(conn=_FakeConn([]))
    db._search_dockets_postgres("test", end_date="2026-01-01")
    assert len(db.conn.cursor_obj.executed) > 0, "No SQL was executed"
    sql, params = db.conn.cursor_obj.executed[0]
    assert "d.modify_date::date <= %s::date" in sql
    assert "2026-01-01" in params


def test_search_dockets_postgres_both_dates():
    db = DBLayer(conn=_FakeConn([]))
    db._search_dockets_postgres("test", start_date="2025-01-01", end_date="2026-01-01")
    assert len(db.conn.cursor_obj.executed) > 0, "No SQL was executed"
    sql, params = db.conn.cursor_obj.executed[0]
    assert "d.modify_date::date >= %s::date" in sql
    assert "d.modify_date::date <= %s::date" in sql
    assert "2025-01-01" in params
    assert "2026-01-01" in params


# --- collection methods ---

def test_get_collections_no_conn_returns_empty():
    assert DBLayer().get_collections("user@example.com") == []


def test_get_collections_returns_rows():
    rows = [(1, "My Collection", "user@example.com", ["DOC-001"])]
    db = DBLayer(conn=_FakeConn(rows))
    result = db.get_collections("user@example.com")
    assert len(result) == 1
    assert result[0]["collection_id"] == 1
    assert result[0]["name"] == "My Collection"
    assert result[0]["docket_ids"] == ["DOC-001"]


def test_get_collections_non_list_docket_ids_returns_empty_list():
    rows = [(1, "My Collection", "user@example.com", None)]
    db = DBLayer(conn=_FakeConn(rows))
    result = db.get_collections("user@example.com")
    assert result[0]["docket_ids"] == []


def test_create_collection_no_conn_returns_minus_one():
    assert DBLayer().create_collection("user@example.com", "Test") == -1


def test_create_collection_returns_new_id():
    conn = _TrackingConn(rows_per_call={2: [(42,)]})
    db = DBLayer(conn=conn)
    result = db.create_collection("user@example.com", "My Collection")
    assert result == 42
    assert conn.committed is True


def test_delete_collection_no_conn_returns_false():
    assert DBLayer().delete_collection(1, "user@example.com") is False


def test_delete_collection_returns_true_when_deleted():
    class DeleteCursor(_FakeCursor):
        def __init__(self):
            super().__init__([])
            self.rowcount = 1

    class DeleteConn:
        def __init__(self):
            self.cursor_obj = DeleteCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    conn = DeleteConn()
    db = DBLayer(conn=conn)
    assert db.delete_collection(1, "user@example.com") is True
    assert conn.committed is True


def test_delete_collection_returns_false_when_not_found():
    class DeleteCursor(_FakeCursor):
        def __init__(self):
            super().__init__([])
            self.rowcount = 0

    class DeleteConn:
        def __init__(self):
            self.cursor_obj = DeleteCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    conn = DeleteConn()
    db = DBLayer(conn=conn)
    assert db.delete_collection(99, "user@example.com") is False


def test_add_docket_to_collection_no_conn_returns_false():
    assert DBLayer().add_docket_to_collection(1, "DOC-001", "user@example.com") is False


def test_add_docket_to_collection_wrong_owner_returns_false():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(conn=conn)
    result = db.add_docket_to_collection(1, "DOC-001", "other@example.com")
    assert result is False
    assert conn.committed is False


def test_add_docket_to_collection_success():
    conn = _TrackingConn(rows_per_call={1: [(1,)], 2: []})
    db = DBLayer(conn=conn)
    result = db.add_docket_to_collection(1, "DOC-001", "user@example.com")
    assert result is True
    assert conn.committed is True
    insert_sql = conn.calls[1][0]
    assert "collection_dockets" in insert_sql


def test_remove_docket_from_collection_no_conn_returns_false():
    assert DBLayer().remove_docket_from_collection(1, "DOC-001", "user@example.com") is False


def test_remove_docket_from_collection_wrong_owner_returns_false():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(conn=conn)
    result = db.remove_docket_from_collection(1, "DOC-001", "other@example.com")
    assert result is False
    assert conn.committed is False


def test_remove_docket_from_collection_success():
    conn = _TrackingConn(rows_per_call={1: [(1,)], 2: []})
    db = DBLayer(conn=conn)
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
    monkeypatch.setattr(db_module, "get_postgres_connection", DBLayer)
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
    db = DBLayer(conn=conn)
    result = db.create_download_job("user@example.com", ["DOC-001", "DOC-002"])
    assert result == str(fake_uuid)
    assert conn.committed is True


def test_create_download_job_upserts_user_first():
    fake_uuid = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(conn=conn)
    db.create_download_job("user@example.com", ["DOC-001"])
    first_sql = conn.calls[0][0]
    assert "INSERT INTO users" in first_sql
    assert "ON CONFLICT" in first_sql


def test_create_download_job_inserts_correct_values():
    fake_uuid = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(conn=conn)
    db.create_download_job("user@example.com", ["DOC-001"], format="csv", include_binaries=True)
    insert_sql, params = conn.calls[1]
    assert "INSERT INTO download_jobs" in insert_sql
    assert params == ("user@example.com", ["DOC-001"], "csv", True)


def test_create_download_job_defaults():
    fake_uuid = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    conn = _TrackingConn(rows_per_call={2: [(fake_uuid,)]})
    db = DBLayer(conn=conn)
    db.create_download_job("user@example.com", ["DOC-001"])
    _, params = conn.calls[1]
    assert params[2] == "zip"
    assert params[3] is False


def test_get_download_job_no_conn_returns_empty_dict():
    assert not DBLayer().get_download_job("some-uuid", "user@example.com")


def test_get_download_job_not_found_returns_empty_dict():
    conn = _TrackingConn(rows_per_call={1: []})
    db = DBLayer(conn=conn)
    result = db.get_download_job("missing-uuid", "user@example.com")
    assert not result


def test_get_download_job_returns_correct_fields():
    job_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    now = datetime.now(timezone.utc)
    row = (job_id, "user@example.com", ["DOC-001"], "zip", False, "pending", None, now, now, now)
    conn = _TrackingConn(rows_per_call={1: [row]})
    db = DBLayer(conn=conn)
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
    db = DBLayer(conn=conn)
    result = db.get_download_job("some-uuid", "other@example.com")
    assert not result
    sql, params = conn.calls[0]
    assert "user_email" in sql
    assert "other@example.com" in params


def test_update_download_job_status_no_conn_returns_false():
    assert DBLayer().update_download_job_status("some-uuid", "complete") is False


def test_update_download_job_status_returns_true_when_updated():
    class RowcountCursor(_FakeCursor):
        def __init__(self):
            super().__init__([])
            self.rowcount = 1

    class RowcountConn:
        def __init__(self):
            self.cursor_obj = RowcountCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    conn = RowcountConn()
    db = DBLayer(conn=conn)
    result = db.update_download_job_status("some-uuid", "complete", s3_path="s3://bucket/file.zip")
    assert result is True
    assert conn.committed is True


def test_update_download_job_status_returns_false_when_not_found():
    class RowcountCursor(_FakeCursor):
        def __init__(self):
            super().__init__([])
            self.rowcount = 0

    class RowcountConn:
        def __init__(self):
            self.cursor_obj = RowcountCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    conn = RowcountConn()
    db = DBLayer(conn=conn)
    result = db.update_download_job_status("missing-uuid", "complete")
    assert result is False


def test_update_download_job_status_sets_correct_params():
    conn = _TrackingConn(rows_per_call={})
    db = DBLayer(conn=conn)
    db.update_download_job_status("my-uuid", "processing", s3_path=None)
    sql, params = conn.calls[0]
    assert "UPDATE download_jobs" in sql
    assert "status" in sql
    assert params[0] == "processing"
    assert params[1] is None
    assert params[2] == "my-uuid"


def test_prune_expired_download_jobs_no_conn_returns_zero():
    assert DBLayer().prune_expired_download_jobs() == 0


def test_prune_expired_download_jobs_returns_deleted_count():
    class PruneCursor(_FakeCursor):
        def __init__(self):
            super().__init__([])
            self.rowcount = 5

    class PruneConn:
        def __init__(self):
            self.cursor_obj = PruneCursor()
            self.committed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

    conn = PruneConn()
    db = DBLayer(conn=conn)
    result = db.prune_expired_download_jobs()
    assert result == 5
    assert conn.committed is True


def test_prune_expired_download_jobs_uses_correct_sql():
    conn = _TrackingConn(rows_per_call={})
    db = DBLayer(conn=conn)
    db.prune_expired_download_jobs()
    sql, _params = conn.calls[0]
    assert "DELETE FROM download_jobs" in sql
    assert "expires_at" in sql
    assert "NOW()" in sql
