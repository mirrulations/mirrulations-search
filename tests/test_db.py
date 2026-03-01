"""
Tests for the database layer (db.py)

Only tests DBLayer wiring, the postgres branch, and module-level
factory functions. Dummy-data behavior tests live in test_mock.py.
"""
# pylint: disable=redefined-outer-name,protected-access
import pytest
import mirrsearch.db as db_module
from mirrsearch.db import DBLayer, get_db


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


def test_get_db_returns_dblayer():
    """Test the get_db factory function returns a DBLayer"""
    db = get_db()
    assert isinstance(db, DBLayer)


# --- Fake postgres helpers ---

class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class _FakeConn:
    def __init__(self, rows):
        self.cursor_obj = _FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        return None


# --- Postgres branch tests ---

def test_search_postgres_branch_without_filter():
    rows = [("D1", "Title One", "CFR 1", "AG", "Rule")]
    db = DBLayer(conn=_FakeConn(rows))

    results = db.search("abc")

    assert results == [
        {
            "docket_id": "D1",
            "title": "Title One",
            "cfrPart": "CFR 1",
            "agency_id": "AG",
            "document_type": "Rule",
        }
    ]
    sql, params = db.conn.cursor_obj.executed
    assert "document_type = %s" not in sql
    assert "agency_id ILIKE %s" not in sql
    assert params == ["%abc%", "%abc%"]


def test_search_postgres_branch_with_filter():
    rows = [("D2", "Title Two", "CFR 2", "AG2", "Proposed Rule")]
    db = DBLayer(conn=_FakeConn(rows))

    db.search("", "Proposed Rule")

    sql, params = db.conn.cursor_obj.executed
    assert "document_type = %s" in sql
    assert params == ["%%", "%%", "Proposed Rule"]


def test_search_postgres_branch_agency_only():
    """Agency filter adds correct ILIKE clause and param"""
    rows = [("D1", "Title One", "CFR 1", "CMS", "Rule")]
    db = DBLayer(conn=_FakeConn(rows))

    db.search("", agency="CMS")

    sql, params = db.conn.cursor_obj.executed
    assert "agency_id ILIKE %s" in sql
    assert params == ["%%", "%%", "%CMS%"]


def test_search_postgres_branch_filter_and_agency():
    """Both filter and agency add their respective clauses"""
    rows = [("D1", "Title One", "CFR 1", "CMS", "Proposed Rule")]
    db = DBLayer(conn=_FakeConn(rows))

    db.search("renal", "Proposed Rule", "CMS")

    sql, params = db.conn.cursor_obj.executed
    assert "document_type = %s" in sql
    assert "agency_id ILIKE %s" in sql
    assert params == ["%renal%", "%renal%", "Proposed Rule", "%CMS%"]


def test_search_postgres_branch_cfr_part():
    """cfr_part_param is accepted but currently commented out pending cfrparts table in RDS"""
    rows = [("D1", "Title One", "42", "CMS", "Proposed Rule")]
    db = DBLayer(conn=_FakeConn(rows))
    db.search("", cfr_part_param="42")
    sql, params = db.conn.cursor_obj.executed
    assert "LIMIT 50" in sql
    assert params == ["%%", "%%"]


# --- Factory function tests ---

def test_get_postgres_connection_uses_env_and_dotenv(monkeypatch):
    called = {"dotenv": False}

    def fake_load():
        called["dotenv"] = True

    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return "conn"

    monkeypatch.setattr(db_module, "LOAD_DOTENV", fake_load)
    monkeypatch.setattr(db_module.psycopg2, "connect", fake_connect)
    monkeypatch.setenv("DB_HOST", "dbhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "dbname")
    monkeypatch.setenv("DB_USER", "dbuser")
    monkeypatch.setenv("DB_PASSWORD", "dbpass")

    db = db_module.get_postgres_connection()

    assert isinstance(db, DBLayer)
    assert db.conn == "conn"
    assert called["dotenv"] is True
    assert captured == {
        "host": "dbhost",
        "port": "5433",
        "database": "dbname",
        "user": "dbuser",
        "password": "dbpass",
    }


def test_get_postgres_connection_uses_aws_secrets(monkeypatch):
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
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return "aws-conn"

    monkeypatch.setattr(db_module, "boto3", fake_boto3)
    monkeypatch.setattr(db_module.psycopg2, "connect", fake_connect)
    monkeypatch.setenv("USE_AWS_SECRETS", "true")

    db = db_module.get_postgres_connection()

    assert isinstance(db, DBLayer)
    assert db.conn == "aws-conn"
    assert captured["host"] == "aws-host"
    assert captured["database"] == "aws-db"


def test_get_secrets_from_aws_raises_without_boto3(monkeypatch):
    """_get_secrets_from_aws raises ImportError when boto3 is None"""
    monkeypatch.setattr(db_module, "boto3", None)
    with pytest.raises(ImportError):
        db_module._get_secrets_from_aws()


def test_get_db_uses_postgres_when_env_set(monkeypatch):
    sentinel = DBLayer(conn="conn")
    monkeypatch.setattr(db_module, "get_postgres_connection", lambda: sentinel)
    monkeypatch.setenv("USE_POSTGRES", "true")

    db = db_module.get_db()

    assert db is sentinel


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
