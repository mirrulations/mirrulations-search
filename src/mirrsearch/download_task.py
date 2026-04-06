import subprocess
import zipfile
import boto3
import os
import psycopg2
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except ImportError:
    LOAD_DOTENV = None
else:
    LOAD_DOTENV = load_dotenv

WORK_DIR = '/tmp/mirrulations'  # staging area for downloads
BUCKET_NAME = TODO  # S3 bucket for storing download packages

# Database connection and job status updates
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
                    error      = %s,
                    updated_at = %s
                WHERE job_id = %s
            """, (status, s3_path, error, datetime.now(timezone.utc), job_id))
        conn.commit()
    finally:
        conn.close()

# CLI commands for fetching and CSV conversion
def run_fetch(docket_id, include_binary=False):
    cmd = ['mirrulations-fetch', docket_id, '--output-folder', WORK_DIR]
    if include_binary:
        cmd.append('--include-binary')
    subprocess.run(cmd, check=True)

def run_csv(docket_id):
    # fetch first to get the JSON comments
    fetch_cmd = ['mirrulations-fetch', docket_id, '--output-folder', WORK_DIR]
    subprocess.run(fetch_cmd, check=True)
    
    # then convert the comments folder to CSV
    comments_path = f'{WORK_DIR}/{docket_id}/raw-data/comments'
    csv_cmd = ['mirrulations-csv', comments_path, '-o', f'{WORK_DIR}/{docket_id}/']
    subprocess.run(csv_cmd, check=True)

# ZIP creation with README
def generate_readme(job_id, docket_ids, format, include_binary):
    return f"""Mirrulations Download
=====================
Job ID:     {job_id}
Generated:  {datetime.now(timezone.utc).isoformat()} UTC
Format:     {format}
Binary:     {'included' if include_binary else 'excluded'}

Dockets:
{chr(10).join(f'  - {d}' for d in docket_ids)}

Note: This download reflects data as of the generation timestamp above.
New comments or documents may have been added since this was created.
This download is available for 2 weeks from the generation date.
"""

def build_zip(job_id, docket_ids, format, include_binary):
    zip_path = f'/tmp/{job_id}.zip'
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('README.txt', generate_readme(job_id, docket_ids, format, include_binary))
        
        for docket_id in docket_ids:
            docket_path = Path(WORK_DIR) / docket_id
            for file in docket_path.rglob('*'):
                if file.is_file():
                    zf.write(file, arcname=file.relative_to(WORK_DIR))
    
    return zip_path

# S3 Download package upload
def upload_to_s3(job_id, zip_path):
    s3 = boto3.client('s3')
    s3_key = f'downloads/{job_id}.zip'
    s3.upload_file(zip_path, BUCKET_NAME, s3_key)
    return s3_key

# Main function to orchestrate the download package creation
def package_dockets(job_id, docket_ids, format, include_binary=False):
    update_job_status(job_id, 'started')
    
    try:
        for docket_id in docket_ids:
            if format == 'raw':
                run_fetch(docket_id, include_binary)
            elif format == 'csv':
                run_csv(docket_id)
        
        zip_path = build_zip(job_id, docket_ids, format, include_binary)
        s3_key = upload_to_s3(job_id, zip_path)
        update_job_status(job_id, 'complete', s3_path=s3_key)

    except Exception as e:
        update_job_status(job_id, 'failed', error=str(e))