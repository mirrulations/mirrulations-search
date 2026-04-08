#!/usr/bin/env python3
"""
Stream-load Federal Register bulk JSON into FR-native Postgres tables.

Usage:
    python db/cfr_and_fr/load_fr_bulk.py
    python db/cfr_and_fr/load_fr_bulk.py /path/to/documents.json
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import ijson
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


BATCH_SIZE = 500
PROGRESS_EVERY = 10_000


INSERT_FR_DOCUMENTS_SQL = """
INSERT INTO federal_register_documents (
    document_number,
    document_id,
    document_title,
    document_type,
    abstract,
    publication_date,
    effective_on,
    docket_ids,
    agency_id,
    agency_names,
    topics,
    significant,
    regulation_id_numbers,
    html_url,
    pdf_url,
    json_url,
    start_page,
    end_page
)
VALUES %s
ON CONFLICT (document_number) DO NOTHING
"""

INSERT_CFRPARTS_SQL = """
INSERT INTO cfrparts (frdocnum, title, cfrpart)
VALUES %s
ON CONFLICT (frdocnum, title, cfrpart) DO NOTHING
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load Federal Register bulk JSON into PostgreSQL tables."
    )
    parser.add_argument(
        "json_path",
        nargs="?",
        default="documents.json",
        help="Path to FR bulk JSON file (default: documents.json)",
    )
    return parser.parse_args()


def load_environment() -> None:
    # Prefer repo-root .env when run from project scripts.
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv()


def db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "database": os.getenv("DB_NAME", "mirrulations"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "sslmode": "verify-full",
        "sslrootcert": "/certs/global-bundle.pem",
    }


def is_numeric(value: Any) -> bool:
    return isinstance(value, (int, str)) and str(value).strip().isdigit()


def pick_agency_id(agencies: Any) -> str | None:
    if not isinstance(agencies, list):
        return None
    for agency in agencies:
        if not isinstance(agency, dict):
            continue
        if agency.get("id") is None:
            continue
        slug = agency.get("slug")
        if isinstance(slug, str) and slug:
            return slug[:20]
        return None
    return None


def as_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item)
        for item in value
        if item is not None and str(item) != ""
    ]


def build_cfr_rows(
    doc: dict[str, Any], document_number: str
) -> list[tuple[Any, ...]]:
    cfr_refs = doc.get("cfr_references")
    if not isinstance(cfr_refs, list):
        return []
    rows = []
    for ref in cfr_refs:
        if not isinstance(ref, dict):
            continue
        title = ref.get("title")
        part = ref.get("part")
        if not is_numeric(title) or not is_numeric(part):
            continue
        rows.append((document_number, str(int(str(title))), str(part)))
    return rows


def build_document_row(doc: dict[str, Any]) -> tuple[Any, ...] | None:
    document_number = doc.get("document_number")
    if not document_number:
        return None

    return (
        str(document_number),
        None,
        doc.get("title"),
        doc.get("type"),
        doc.get("abstract"),
        doc.get("publication_date"),
        doc.get("effective_on"),
        as_list_of_strings(doc.get("docket_ids")),
        pick_agency_id(doc.get("agencies")),
        as_list_of_strings(doc.get("agency_names")),
        as_list_of_strings(doc.get("topics")),
        doc.get("significant"),
        as_list_of_strings(doc.get("regulation_id_numbers")),
        doc.get("html_url"),
        doc.get("pdf_url"),
        doc.get("json_url"),
        doc.get("start_page"),
        doc.get("end_page"),
    )


def flush_batch(
    cur: Any,
    conn: Any,
    doc_rows: list[tuple[Any, ...]],
    cfr_rows: list[tuple[Any, ...]],
) -> int:
    if doc_rows:
        execute_values(
            cur, INSERT_FR_DOCUMENTS_SQL, doc_rows, page_size=BATCH_SIZE
        )
    if cfr_rows:
        execute_values(
            cur, INSERT_CFRPARTS_SQL, cfr_rows, page_size=BATCH_SIZE * 4
        )
    conn.commit()
    return 0


def main() -> None:
    args = parse_args()
    json_path = Path(args.json_path).expanduser().resolve()
    if not json_path.exists():
        raise SystemExit(f"JSON file not found: {json_path}")

    load_environment()

    processed = 0
    skipped = 0

    doc_rows: list[tuple[Any, ...]] = []
    cfr_rows: list[tuple[Any, ...]] = []

    print(f"Loading: {json_path}")
    print("Starting stream parse + batch insert...")

    conn = psycopg2.connect(**db_config())
    try:
        with conn.cursor() as cur, json_path.open("rb") as handle:
            for doc in ijson.items(handle, "item"):
                processed += 1
                row = build_document_row(doc)
                if row is None:
                    skipped += 1
                else:
                    doc_rows.append(row)
                    cfr_rows.extend(build_cfr_rows(doc, row[0]))

                if len(doc_rows) >= BATCH_SIZE:
                    flush_batch(cur, conn, doc_rows, cfr_rows)
                    doc_rows.clear()
                    cfr_rows.clear()

                if processed % PROGRESS_EVERY == 0:
                    print(
                        f"processed={processed:,} skipped={skipped:,}"
                    )

            if doc_rows:
                flush_batch(cur, conn, doc_rows, cfr_rows)
                doc_rows.clear()
                cfr_rows.clear()

        print("Load complete.")
        print(f"processed={processed:,} skipped={skipped:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()