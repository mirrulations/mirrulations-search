"""Focused tests for the Redis download worker."""
import importlib
import sys
import types
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if "redis" not in sys.modules:
    sys.modules["redis"] = types.SimpleNamespace(
        Redis=object,
        exceptions=types.SimpleNamespace(ConnectionError=Exception),
    )

worker = importlib.import_module("worker")


class _DummyConn: # pylint: disable=too-few-public-methods
    def close(self):
        return None


def test_resolve_command_prefers_search_venv(monkeypatch, tmp_path):
    """Worker should prefer the active service venv entrypoint."""
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    cli = venv_bin / "mirrulations-fetch"
    cli.write_text("#!/bin/sh\n")
    cli.chmod(0o755)

    fake_python = venv_bin / "python"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)

    monkeypatch.setattr(worker.sys, "executable", str(fake_python))
    monkeypatch.delenv("FETCH_REPO_DIR", raising=False)

    assert worker._resolve_command("mirrulations-fetch", "FETCH_REPO_DIR") == [str(cli)] # pylint: disable=protected-access


def test_resolve_command_falls_back_to_repo_checkout(monkeypatch, tmp_path):
    """Worker should use the repo-local venv when provided by environment."""
    repo_dir = tmp_path / "mirrulations-fetch"
    repo_cli = repo_dir / ".venv" / "bin" / "mirrulations-fetch"
    repo_cli.parent.mkdir(parents=True)
    repo_cli.write_text("#!/bin/sh\n")
    repo_cli.chmod(0o755)

    missing_python = tmp_path / "missing" / "python"
    monkeypatch.setattr(worker.sys, "executable", str(missing_python))
    monkeypatch.setenv("FETCH_REPO_DIR", str(repo_dir))
    monkeypatch.setattr(worker.shutil, "which", lambda _name: None)

    assert worker._resolve_command("mirrulations-fetch", "FETCH_REPO_DIR") == [str(repo_cli)] # pylint: disable=protected-access


def test_process_job_marks_processing_before_ready(monkeypatch, tmp_path):
    """Worker should transition jobs through processing before ready."""
    statuses = []

    def fake_update_job_status(conn, job_id, status, s3_path=None): # pylint: disable=unused-argument
        statuses.append((job_id, status, s3_path))

    monkeypatch.setattr(worker, "_get_pg_conn", lambda: _DummyConn()) # pylint: disable=unnecessary-lambda
    monkeypatch.setattr(worker, "_update_job_status", fake_update_job_status)
    monkeypatch.setattr(worker, "_build_zip", lambda *_args: str(tmp_path / "job.zip"))
    monkeypatch.setattr(worker, "_upload_to_s3", lambda *_args: "s3://bucket/downloads/job-1.zip")

    payload = (
    '{"job_id":"job-1","docket_ids":["CMS-2025-0240"],'
    '"format":"raw","include_binaries":false,"user_email":"test@example.com"}'
)
    worker._process_job(payload) # pylint: disable=protected-access

    assert statuses == [
        ("job-1", "processing", None),
        ("job-1", "ready", "s3://bucket/downloads/job-1.zip"),
    ]
