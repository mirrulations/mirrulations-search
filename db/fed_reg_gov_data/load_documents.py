#!/usr/bin/env python3
"""
load_documents_s3.py — Bulk-load regulations.gov document JSON files directly
from S3 into the documents table in the Mirrulations PostgreSQL database.

WHAT IT DOES:
    Paginates through all files in s3://mirrulations/raw-data/ matching the
    pattern raw-data/<agency>/Docket/text-<docketID>/documents/<documentID>.json,
    streams each JSON file directly from S3 using a thread pool (no disk needed),
    maps the fields to the database schema, and inserts them in batches using
    upsert (ON CONFLICT DO UPDATE).

    A checkpoint file tracks which S3 keys have been successfully inserted.
    If the script is interrupted, re-running it will skip already-processed
    files and resume from where it left off.

HOW TO USE:
    1. Ensure load_s3.env exists with your DB credentials:

        DB_HOST=your-rds-endpoint.rds.amazonaws.com
        DB_PORT=5432
        DB_NAME=your_db
        DB_USER=your_user
        DB_PASSWORD=your_password

    2. Ensure the RDS SSL certificate is present at /certs/global-bundle.pem.

    3. Run the script:

        Without date filter:
            nohup python3 load_documents_s3.py > ~/load_s3_output.log 2>&1 &

        With date filter (gap backfill):
            nohup python3 load_documents_s3.py --start-date 2025-03-20 --end-date 2025-04-20 > ~/load_s3_output.log 2>&1 &

    To restart from scratch, delete the checkpoint file:
        rm ~/load_s3_checkpoint.txt

    4. Check the output:
        tail -f ~/load_s3_output.log
"""

import os
import json
import logging
import argparse
import threading
import boto3
import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from psycopg2.extras import execute_values
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("load_s3.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host":        os.environ.get("DB_HOST"),
    "port":        int(os.environ.get("DB_PORT", 5432)),
    "dbname":      os.environ.get("DB_NAME"),
    "user":        os.environ.get("DB_USER"),
    "password":    os.environ.get("DB_PASSWORD"),
    "sslmode":     "verify-full",
    "sslrootcert": "/certs/global-bundle.pem",
}

S3_BUCKET       = os.environ.get("S3_BUCKET", "mirrulations")
S3_PREFIX       = os.environ.get("S3_PREFIX", "raw-data/")
CHECKPOINT_FILE = Path(os.environ.get("CHECKPOINT_FILE", os.path.expanduser("~/load_s3_checkpoint.txt")))
BATCH_SIZE      = 2000
MAX_WORKERS     = 20
MAX_IN_FLIGHT   = MAX_WORKERS * 4
_thread_local = threading.local()

def get_s3_client():
    if not hasattr(_thread_local, "s3"):
        _thread_local.s3 = boto3.client("s3")
    return _thread_local.s3


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            keys = {line.strip() for line in f if line.strip()}
        log.info("Resuming — %d S3 keys already processed", len(keys))
        return keys
    return set()


def save_checkpoint(keys):
    with open(CHECKPOINT_FILE, "a") as f:
        for k in keys:
            f.write(k + "\n")


def map_document(raw, s3_key):
    try:
        data  = raw["data"]
        attr  = data["attributes"]
        links = data["links"]
    except KeyError as e:
        log.warning("Skipping %s — malformed JSON, missing key: %s", s3_key, e)
        return None

    document_id       = data.get("id")
    docket_id         = attr.get("docketId") or (document_id.rsplit("-", 1)[0] if document_id else None)
    modify_date       = attr.get("modifyDate")
    doc_type          = attr.get("documentType")
    document_api_link = links.get("self")
    agency_id         = attr.get("agencyId")

    required = {
        "document_id":       document_id,
        "docket_id":         docket_id,
        "modify_date":       modify_date,
        "document_type":     doc_type,
        "document_api_link": document_api_link,
        "agency_id":         agency_id,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        log.warning("Skipping %s — missing required field(s): %s", document_id or s3_key, missing)
        return None

    return {
        "document_id":               document_id,
        "docket_id":                 docket_id,
        "document_api_link":         document_api_link,
        "address1":                  attr.get("address1"),
        "address2":                  attr.get("address2"),
        "agency_id":                 agency_id,
        "is_late_comment":           attr.get("allowLateComments"),
        "author_date":               attr.get("authorDate"),
        "comment_category":          attr.get("category"),
        "city":                      attr.get("city"),
        "comment":                   attr.get("comment"),
        "comment_end_date":          attr.get("commentEndDate"),
        "comment_start_date":        attr.get("commentStartDate"),
        "country":                   attr.get("country"),
        "document_type":             doc_type,
        "effective_date":            attr.get("effectiveDate"),
        "email":                     attr.get("email"),
        "fax":                       attr.get("fax"),
        "flex_field1":               attr.get("field1"),
        "flex_field2":               attr.get("field2"),
        "first_name":                attr.get("firstName"),
        "submitter_gov_agency":      attr.get("govAgency"),
        "submitter_gov_agency_type": attr.get("govAgencyType"),
        "implementation_date":       attr.get("implementationDate"),
        "last_name":                 attr.get("lastName"),
        "modify_date":               modify_date,
        "is_open_for_comment":       attr.get("openForComment", False),
        "submitter_org":             attr.get("organization"),
        "phone":                     attr.get("phone"),
        "posted_date":               attr.get("postedDate"),
        "postmark_date":             attr.get("postmarkDate"),
        "reason_withdrawn":          attr.get("reasonWithdrawn"),
        "receive_date":              attr.get("receiveDate"),
        "reg_writer_instruction":    attr.get("regWriterInstruction"),
        "restriction_reason":        attr.get("restrictReason"),
        "restriction_reason_type":   attr.get("restrictReasonType"),
        "state_province_region":     attr.get("stateProvinceRegion"),
        "subtype":                   attr.get("subtype"),
        "document_title":            attr.get("title"),
        "topics":                    attr.get("topics"),
        "is_withdrawn":              attr.get("withdrawn", False),
        "postal_code":               attr.get("zip"),
        "frdocnum":                  attr.get("frDocNum"),
    }


def fetch_and_map(bucket, key):
    """Fetch a single S3 object and map it. Returns (doc, key) or (None, key)."""
    try:
        s3       = get_s3_client()
        response = s3.get_object(Bucket=bucket, Key=key)
        raw      = json.load(response["Body"])
        doc      = map_document(raw, key)
        return doc, key
    except json.JSONDecodeError as e:
        log.warning("Skipping %s — invalid JSON: %s", key, e)
        return None, key
    except Exception as e:
        log.warning("Skipping %s — unexpected error: %s", key, e)
        return None, key


def list_eligible_keys(bucket, prefix, processed, start_date=None, end_date=None):
    """Paginate S3 and yield keys that match the date filter and aren't checkpointed."""
    s3        = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    total     = 0

    date_range_msg = ""
    if start_date or end_date:
        date_range_msg = f" (LastModified filter: {start_date or '*'} -> {end_date or '*'})"
    log.info("Scanning s3://%s/%s ...%s", bucket, prefix, date_range_msg)

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if "/documents/" not in key or not key.endswith(".json"):
                continue
            if key in processed:
                continue
            if start_date and obj["LastModified"] < start_date:
                continue
            if end_date and obj["LastModified"] > end_date:
                continue

            total += 1
            if total % 10_000 == 0:
                log.info("Listed %d eligible S3 keys so far...", total)

            yield key


COLUMNS = [
    "document_id", "docket_id", "document_api_link", "address1", "address2",
    "agency_id", "is_late_comment", "author_date", "comment_category", "city",
    "comment", "comment_end_date", "comment_start_date", "country",
    "document_type", "effective_date", "email", "fax", "flex_field1",
    "flex_field2", "first_name", "submitter_gov_agency",
    "submitter_gov_agency_type", "implementation_date", "last_name",
    "modify_date", "is_open_for_comment", "submitter_org", "phone",
    "posted_date", "postmark_date", "reason_withdrawn", "receive_date",
    "reg_writer_instruction", "restriction_reason", "restriction_reason_type",
    "state_province_region", "subtype", "document_title", "topics",
    "is_withdrawn", "postal_code", "frdocnum",
]

INSERT_SQL = f"""
    INSERT INTO documents ({', '.join(COLUMNS)})
    VALUES %s
    ON CONFLICT (document_id) DO UPDATE SET
        modify_date          = EXCLUDED.modify_date,
        is_open_for_comment  = EXCLUDED.is_open_for_comment,
        is_withdrawn         = EXCLUDED.is_withdrawn,
        frdocnum             = COALESCE(EXCLUDED.frdocnum, documents.frdocnum),
        document_title       = EXCLUDED.document_title,
        topics               = EXCLUDED.topics,
        comment_end_date     = EXCLUDED.comment_end_date,
        comment_start_date   = EXCLUDED.comment_start_date,
        posted_date          = EXCLUDED.posted_date
"""


def insert_batch(cursor, batch):
    seen = {}
    for doc in batch:
        seen[doc["document_id"]] = doc
    rows = [tuple(doc[col] for col in COLUMNS) for doc in seen.values()]
    execute_values(cursor, INSERT_SQL, rows)


def parse_args():
    parser = argparse.ArgumentParser(description="Bulk-load S3 document JSON files into RDS.")
    parser.add_argument("--start-date", metavar="YYYY-MM-DD", help="Only process S3 objects with LastModified >= this date (UTC)")
    parser.add_argument("--end-date",   metavar="YYYY-MM-DD", help="Only process S3 objects with LastModified <= this date (UTC)")
    return parser.parse_args()


def main():
    args = parse_args()

    start_date = (
        datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.start_date else None
    )
    end_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
        if args.end_date else None
    )

    processed = load_checkpoint()

    log.info("Connecting to RDS at %s ...", DB_CONFIG["host"])
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    batch           = []
    batch_keys      = []
    skipped_keys    = []
    total_inserted  = 0
    total_skipped   = 0

    key_gen = list_eligible_keys(S3_BUCKET, S3_PREFIX, processed, start_date, end_date)

    def flush_batch():
        nonlocal total_inserted, total_skipped
        if not batch:
            return
        try:
            insert_batch(cursor, batch)
            conn.commit()
            save_checkpoint(batch_keys)
            total_inserted += len(batch)
            log.info("Inserted %d rows (total: %d)", len(batch), total_inserted)
        except Exception as e:
            conn.rollback()
            log.error("Batch insert failed, rolling back: %s", e)
            total_skipped += len(batch)
        finally:
            batch.clear()
            batch_keys.clear()

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            pending = {}

            for key in key_gen:
                pending[executor.submit(fetch_and_map, S3_BUCKET, key)] = key
                if len(pending) < MAX_IN_FLIGHT:
                    continue

                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    del pending[future]
                    doc, fkey = future.result()
                    if doc:
                        batch.append(doc)
                        batch_keys.append(fkey)
                    else:
                        skipped_keys.append(fkey)
                    if len(batch) >= BATCH_SIZE:
                        flush_batch()
                    if skipped_keys and len(skipped_keys) >= BATCH_SIZE:
                        save_checkpoint(skipped_keys)
                        skipped_keys.clear()

            # Drain remaining in-flight futures
            for future in as_completed(pending):
                doc, fkey = future.result()
                if doc:
                    batch.append(doc)
                    batch_keys.append(fkey)
                else:
                    skipped_keys.append(fkey)
                if len(batch) >= BATCH_SIZE:
                    flush_batch()

        flush_batch()
        if skipped_keys:
            save_checkpoint(skipped_keys)

    finally:
        cursor.close()
        conn.close()

    log.info("Done. Inserted: %d | Skipped/malformed: %d", total_inserted, total_skipped)


if __name__ == "__main__":
    main()