import subprocess
import zipfile
import boto3
import os
import psycopg2
from pathlib import Path
from datetime import datetime, timezone
from redis import Redis
from rq import Queue

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WORK_DIR = '/tmp/mirrulations-downloads'  # staging area for downloads
BUCKET_NAME = os.getenv("BUCKET_NAME")  # S3 bucket for storing download packages

# QUEUE
def get_queue():
    redis_conn = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
    )
    return Queue(connection=redis_conn)

def enqueue_package_dockets(job_id, docket_ids, format):
    """Call this from the web app to enqueue a download job instead of calling package_dockets directly."""
    q = get_queue()
    q.enqueue(package_dockets, job_id, docket_ids, format)

# DATABASE
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "your_db"),
        user=os.getenv("DB_USER", "your_user"),
        password=os.getenv("DB_PASSWORD", "your_password")
    )

def update_job_status(job_id, status, s3_path=None, error=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE download_jobs
                SET status     = %s,
                    s3_path    = %s,
                    updated_at = %s
                WHERE job_id = %s
            """, (status, s3_path, datetime.now(timezone.utc), job_id))
        conn.commit()
    finally:
        conn.close()

# CLI TOOLS
def run_fetch(docket_id):
    cmd = ['mirrulations-fetch', docket_id, '--output-folder', WORK_DIR]
    subprocess.run(cmd, check=True)

def run_csv(docket_id):
    # fetch first to get the JSON comments
    fetch_cmd = ['mirrulations-fetch', docket_id, '--output-folder', WORK_DIR]
    subprocess.run(fetch_cmd, check=True)

    # then convert the comments folder to CSV
    comments_path = f'{WORK_DIR}/{docket_id}/raw-data/comments'
    csv_cmd = ['mirrulations-csv', comments_path, '-o', f'{WORK_DIR}/{docket_id}/']
    subprocess.run(csv_cmd, check=True)

# ZIP
def generate_readme(job_id, docket_ids, format):
    return f"""Mirrulations Download
=====================
Job ID:     {job_id}
Generated:  {datetime.now(timezone.utc).isoformat()} UTC
Format:     {format}

Dockets:
{chr(10).join(f'  - {d}' for d in docket_ids)}

Note: This download reflects data as of the generation timestamp above.
New comments or documents may have been added since this was created.
This download is available for 7 days from the generation date.
"""

def build_zip(job_id, docket_ids, format):
    zip_path = f'/tmp/{job_id}.zip'
 
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('README.txt', generate_readme(job_id, docket_ids, format))
 
        for docket_id in docket_ids:
            docket_path = Path(WORK_DIR) / docket_id
            for file in docket_path.rglob('*'):
                if file.is_file():
                    zf.write(file, arcname=file.relative_to(WORK_DIR))
 
    return zip_path

# S3
def upload_to_s3(job_id, zip_path):
    s3 = boto3.client('s3')
    s3_key = f'downloads/{job_id}.zip'
    s3.upload_file(zip_path, BUCKET_NAME, s3_key)
    return s3_key

# MAIN TASK (called by RQ worker, never directly)
def package_dockets(job_id, docket_ids, format):
    """This function is executed by the RQ worker in the background.
    Do not call this directly from the web app — use enqueue_package_dockets instead."""
    update_job_status(job_id, 'started')

    try:
        for docket_id in docket_ids:
            if format == 'raw':
                run_fetch(docket_id)
            elif format == 'csv':
                run_csv(docket_id)

        zip_path = build_zip(job_id, docket_ids, format)
        s3_key = upload_to_s3(job_id, zip_path)
        update_job_status(job_id, 'complete', s3_path=s3_key)

    except Exception as e:
        update_job_status(job_id, 'failed', error=str(e))