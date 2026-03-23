#!/usr/bin/env python3
"""Standalone loader for HQ clean jsonl.gz package into dockets/documents."""

"""quick copy paste
## Load into Postgres schema

```bash
python3 load_jsonl_gz_to_db.py \
  --input-root "hq_clean/by_agency" \
  --db-host localhost \
  --db-port 5432 \
  --db-name mirrulations \
  --db-user matt \
  --db-password ""
```

Dry-run only:

```bash
python3 load_jsonl_gz_to_db.py --input-root "hq_clean/by_agency" --dry-run
``` """

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load HQ clean jsonl.gz files into Postgres dockets/documents."
    )
    parser.add_argument("--input-root", default="hq_clean/by_agency")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-host", default="localhost")
    parser.add_argument("--db-port", default="5432")
    parser.add_argument("--db-name", default="mirrulations")
    parser.add_argument("--db-user", default="postgres")
    parser.add_argument("--db-password", default="")
    return parser.parse_args()


def deterministic_document_id(document_number: str, docket_id: str) -> str:
    digest = hashlib.sha1(f"{document_number}|{docket_id}".encode("utf-8")).hexdigest()
    return f"fr-{digest[:47]}"


def iter_records(input_root: Path):
    for fp in sorted(input_root.glob("**/*.jsonl.gz")):
        with gzip.open(fp, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def validate_record(record: dict) -> tuple[dict | None, str | None]:
    canonical = record.get("canonical_docket_ids") or []
    if not canonical:
        return None, "missing_canonical_docket_id"

    docket_id = str(canonical[0]).strip().upper()
    if not docket_id:
        return None, "invalid_canonical_docket_id"
    if len(docket_id) > 50:
        return None, "docket_id_too_long"

    agency_id = (record.get("agency_id") or "").strip()[:20]
    if not agency_id:
        return None, "missing_agency_id"

    document_number = (record.get("document_number") or "").strip()
    if not document_number:
        return None, "missing_document_number"

    document_type = (record.get("document_type") or "").strip()
    if not document_type:
        return None, "missing_document_type"

    publication_date = record.get("publication_date")
    if not publication_date:
        return None, "missing_publication_date"

    document_api_link = (record.get("json_url") or record.get("html_url") or "").strip()[:2000]
    if not document_api_link:
        return None, "missing_document_api_link"

    row = {
        "docket_id": docket_id,
        "docket_api_link": f"https://api.regulations.gov/v4/dockets/{docket_id}"[:2000],
        "agency_id": agency_id,
        "docket_type": document_type[:50],
        "modify_date": f"{publication_date}T00:00:00+00:00",
        "docket_title": (record.get("document_title") or "")[:500] or None,
        "document_id": deterministic_document_id(document_number, docket_id),
        "document_api_link": document_api_link,
        "document_type": document_type[:30],
        "posted_date": f"{publication_date}T00:00:00+00:00",
        "document_title": (record.get("document_title") or "")[:500] or None,
    }
    return row, None


def connect_psycopg2(args: argparse.Namespace):
    import psycopg2  # imported lazily so dry-run works without dependency
    return psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        database=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )


def main() -> None:
    args = parse_args()
    input_root = Path(args.input_root).expanduser().resolve()

    accepted = []
    rejects = Counter()
    for record in iter_records(input_root):
        row, reason = validate_record(record)
        if reason:
            rejects[reason] += 1
        else:
            accepted.append(row)

    print(
        json.dumps(
            {
                "mode": "dry_run" if args.dry_run else "apply",
                "input_root": str(input_root),
                "accepted_rows": len(accepted),
                "rejected_rows": sum(rejects.values()),
                "rejected_by_reason": dict(rejects),
                "accepted_unique_dockets": len({r["docket_id"] for r in accepted}),
                "accepted_unique_document_ids": len({r["document_id"] for r in accepted}),
            },
            indent=2,
        )
    )

    if args.dry_run:
        return

    conn = connect_psycopg2(args)
    try:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values

            docket_by_id = {}
            for r in accepted:
                docket_by_id[r["docket_id"]] = (
                    r["docket_id"],
                    r["docket_api_link"],
                    r["agency_id"],
                    r["docket_type"],
                    r["modify_date"],
                    r["docket_title"],
                )
            execute_values(
                cur,
                """
                INSERT INTO dockets (docket_id, docket_api_link, agency_id, docket_type, modify_date, docket_title)
                VALUES %s
                ON CONFLICT (docket_id) DO UPDATE
                SET agency_id = EXCLUDED.agency_id,
                    docket_type = EXCLUDED.docket_type,
                    modify_date = EXCLUDED.modify_date,
                    docket_title = EXCLUDED.docket_title
                """,
                list(docket_by_id.values()),
            )

            doc_by_id = {}
            for r in accepted:
                doc_by_id[r["document_id"]] = (
                    r["document_id"],
                    r["docket_id"],
                    r["document_api_link"],
                    r["agency_id"],
                    r["document_type"],
                    r["modify_date"],
                    r["posted_date"],
                    r["document_title"],
                )
            execute_values(
                cur,
                """
                INSERT INTO documents (
                    document_id, docket_id, document_api_link, agency_id,
                    document_type, modify_date, posted_date, document_title
                )
                VALUES %s
                ON CONFLICT (document_id) DO UPDATE
                SET docket_id = EXCLUDED.docket_id,
                    document_api_link = EXCLUDED.document_api_link,
                    agency_id = EXCLUDED.agency_id,
                    document_type = EXCLUDED.document_type,
                    modify_date = EXCLUDED.modify_date,
                    posted_date = EXCLUDED.posted_date,
                    document_title = EXCLUDED.document_title
                """,
                list(doc_by_id.values()),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

