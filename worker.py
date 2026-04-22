"""
Download worker — polls Redis for jobs, runs mirrulations-fetch or mirrulations-csv,
zips the output, uploads to S3, and updates the Postgres job status.

Environment variables:
  REDIS_HOST        (default: localhost)
  REDIS_PORT        (default: 6379)
  REDIS_DB          (default: 0)
  S3_BUCKET         S3 bucket name for download uploads (required)
  FETCH_REPO_DIR    path to mirrulations-fetch checkout (default: ../mirrulations-fetch)
  CSV_REPO_DIR      path to mirrulations-csv checkout   (default: ../mirrulations-csv)
  DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD   Postgres credentials
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

import boto3
import psycopg2
import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

REDIS_QUEUE = "download_queue"
POLL_TIMEOUT = 5  # seconds to block-wait on Redis BLPOP


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        decode_responses=True,
    )


def _get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "your_db"),
        user=os.getenv("DB_USER", "your_user"),
        password=os.getenv("DB_PASSWORD", "your_password"),
    )


def _update_job_status(conn, job_id, status, s3_path=None):
    sql = """
        UPDATE download_jobs
        SET status = %s, s3_path = %s, updated_at = NOW()
        WHERE job_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (status, s3_path, job_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Download execution
# ---------------------------------------------------------------------------

def _search_paths_for_command(command_name, repo_env_var):
    """Return candidate executable paths for a CLI command."""
    candidates = []
    venv_bin = os.path.dirname(sys.executable)
    candidates.append(os.path.join(venv_bin, command_name))

    repo_dir = os.getenv(repo_env_var, "").strip()
    if repo_dir:
        candidates.extend([
            os.path.join(repo_dir, ".venv", "bin", command_name),
            os.path.join(repo_dir, "venv", "bin", command_name),
            os.path.join(repo_dir, "bin", command_name),
        ])
    return candidates


def _repo_script_path(repo_dir, command_name):
    if not repo_dir:
        return None
    if command_name == "mirrulations-fetch":
        return os.path.join(repo_dir, "mirrulations_fetch", "download_docket.py")
    if command_name == "mirrulations-csv":
        return os.path.join(repo_dir, "mirrulations_csv", "docket_to_csv.py")
    return None


def _resolve_command(command_name, repo_env_var):
    """Resolve a worker CLI executable from the service venv, repo, or PATH."""
    for candidate in _search_paths_for_command(command_name, repo_env_var):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return [candidate]

    from_path = shutil.which(command_name)
    if from_path:
        return [from_path]

    repo_dir = os.getenv(repo_env_var, "").strip()
    repo_script = _repo_script_path(repo_dir, command_name)
    if repo_script and os.path.isfile(repo_script):
        return [sys.executable, repo_script]

    raise FileNotFoundError(
        f"Could not find '{command_name}'. "
        f"Install it into the worker venv or set {repo_env_var} to a checkout with the CLI."
    )


def _run_fetch(docket_ids, output_dir, include_binaries):
    """Run mirrulations-fetch for each docket into output_dir."""
    fetch_cmd = _resolve_command("mirrulations-fetch", "FETCH_REPO_DIR")
    for docket_id in docket_ids:
        cmd = [*fetch_cmd, docket_id, "--output-folder", output_dir]
        if include_binaries:
            cmd.append("--include-binary")
        log.info("Running fetch for docket %s", docket_id)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
        if result.returncode != 0:
            log.error("fetch failed for %s:\n%s", docket_id, result.stderr)
            raise RuntimeError(f"mirrulations-fetch failed for docket {docket_id}")


def _run_csv(docket_ids, output_dir):
    """Run mirrulations-fetch then mirrulations-csv for each docket into output_dir."""
    fetch_cmd = _resolve_command("mirrulations-fetch", "FETCH_REPO_DIR")
    csv_cmd = _resolve_command("mirrulations-csv", "CSV_REPO_DIR")
    for docket_id in docket_ids:
        # First fetch the raw data
        log.info("Fetching raw data for docket %s", docket_id)
        result = subprocess.run(
            [*fetch_cmd, docket_id, "--output-folder", output_dir],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode != 0:
            log.error("fetch failed for %s:\n%s", docket_id, result.stderr)
            raise RuntimeError(f"mirrulations-fetch failed for docket {docket_id}")

        # Then convert comments to CSV
        comments_dir = os.path.join(output_dir, docket_id, "raw-data", "comments")
        log.info("Converting to CSV for docket %s", docket_id)
        result = subprocess.run(
            [*csv_cmd, comments_dir, "-o", output_dir],
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if result.returncode != 0:
            log.error("csv export failed for %s:\n%s", docket_id, result.stderr)
            raise RuntimeError(f"mirrulations-csv failed for docket {docket_id}")


def _zip_output(source_dir, zip_path):
    """Zip everything in source_dir into zip_path."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, source_dir)
                zf.write(full, arcname)
    log.info("Zipped output to %s", zip_path)


def _upload_to_s3(zip_path, job_id):
    """Upload zip_path to S3 and return the s3:// URI.
    Falls back to saving locally if S3_BUCKET is not set."""
    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        local_dir = os.path.join(os.path.dirname(__file__), "downloads")
        os.makedirs(local_dir, exist_ok=True)
        dest = os.path.join(local_dir, f"{job_id}.zip")
        shutil.copy2(zip_path, dest)
        log.info("S3_BUCKET not set — saved locally to %s", dest)
        return f"local://{dest}"
    key = f"downloads/{job_id}.zip"
    s3 = boto3.client("s3")
    log.info("Uploading %s to s3://%s/%s", zip_path, bucket, key)
    s3.upload_file(zip_path, bucket, key)
    return f"s3://{bucket}/{key}"


# ---------------------------------------------------------------------------
# Job processing
# ---------------------------------------------------------------------------

def _build_zip(job_id, docket_ids, data_format, include_binaries, work_dir):
    """Run fetch/csv, zip the output, return (zip_path)."""
    output_dir = os.path.join(work_dir, "output")
    os.makedirs(output_dir)
    if data_format == "csv":
        _run_csv(docket_ids, output_dir)
    else:
        _run_fetch(docket_ids, output_dir, include_binaries)
    zip_path = os.path.join(work_dir, f"{job_id}.zip")
    _zip_output(output_dir, zip_path)
    return zip_path


def _parse_payload(payload_str):
    payload = json.loads(payload_str)
    return (
        payload["job_id"],
        payload["docket_ids"],
        payload["format"],
        payload.get("include_binaries", False),
    )


def _process_job(payload_str):  # pylint: disable=too-many-locals
    job_id, docket_ids, data_format, include_binaries = _parse_payload(payload_str)
    log.info("Processing job %s: format=%s dockets=%s", job_id, data_format, docket_ids)
    conn = _get_pg_conn()
    try:
        _update_job_status(conn, job_id, "processing")
        with tempfile.TemporaryDirectory() as work_dir:
            zip_path = _build_zip(job_id, docket_ids, data_format, include_binaries, work_dir)
            s3_uri = _upload_to_s3(zip_path, job_id)
        _update_job_status(conn, job_id, "ready", s3_uri)
        log.info("Job %s complete: %s", job_id, s3_uri)
    except Exception as exc:  # pylint: disable=broad-except
        log.exception("Job %s failed: %s", job_id, exc)
        try:
            _update_job_status(conn, job_id, "failed")
        except Exception:  # pylint: disable=broad-except
            log.exception("Could not update job %s to failed", job_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    log.info("Worker starting — listening on Redis queue '%s'", REDIS_QUEUE)
    r = _get_redis()

    while True:
        try:
            item = r.blpop(REDIS_QUEUE, timeout=POLL_TIMEOUT)
            if item is None:
                continue
            _, payload_str = item
            _process_job(payload_str)
        except redis.exceptions.ConnectionError as exc:
            log.error("Redis connection error: %s — retrying in 5s", exc)
            time.sleep(5)
        except KeyboardInterrupt:
            log.info("Worker stopped.")
            break


if __name__ == "__main__":
    main()
