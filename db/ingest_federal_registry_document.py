#!/usr/bin/env python3
"""
Ingest a single Federal Register document JSON file into Postgres.

Populates:
- federal_register_documents (one row per FR document_number)
- cfrparts (one row per (frdocnum, title, cfrpart) from cfr_references)

Usage:
  python ingest_fr_document.py --json data/runs/CMS_2026/federal_register/2025-21121.json

Connection:
  Uses DATABASE_URL from environment (e.g. postgres://user:pass@host:port/dbname),
  or falls back to PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2
from psycopg2.extras import register_default_jsonb


def load_env() -> None:
    """Load .env from repo root (or nearest parent) if present."""
    start = Path(__file__).resolve()
    candidates = [
        start.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    candidates.extend(p / ".env" for p in start.parents[:5])

    for env_path in candidates:
        if env_path.exists() and env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            return

def _coalesce_env(*names: str, default: str = "") -> str:
    """First non-empty env var value, else default."""
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return default


def _parse_int_env(*names: str, default: int) -> int:
    """Parse int from first non-empty env var; empty/invalid -> default."""
    raw = _coalesce_env(*names, default="")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_connection():
    load_env()
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn)
    # Fallback to individual PG* env vars
    return psycopg2.connect(
        host=_coalesce_env("PGHOST", "DB_HOST", default="localhost"),
        port=_parse_int_env("PGPORT", "DB_PORT", default=5432),
        user=_coalesce_env("PGUSER", "DB_USER", default="postgres"),
        password=_coalesce_env("PGPASSWORD", "DB_PASSWORD", default=""),
        dbname=_coalesce_env("PGDATABASE", "DB_NAME", default="postgres"),
    )


def load_fr_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse JSON at {path}: {e}") from e


def extract_agency_fields(doc: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    agencies = doc.get("agencies") or []
    if not isinstance(agencies, list) or not agencies:
        return None, []
    first = agencies[0] or {}
    # FR agency id is numeric; store as string to fit VARCHAR(20)
    agency_id = str(first.get("id")) if first.get("id") is not None else None
    names = [a.get("name") for a in agencies if isinstance(a, dict) and a.get("name")]
    return agency_id, names


def extract_cfrparts(doc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Return list of (frdocnum, title, cfrpart) tuples from cfr_references.
    Skips malformed references.
    """
    fr_num = str(doc.get("document_number") or "").strip()
    out: List[Tuple[str, str, str]] = []
    if not fr_num:
        return out
    for ref in doc.get("cfr_references") or []:
        if not isinstance(ref, dict):
            continue
        title = ref.get("title")
        part = ref.get("part") or ref.get("parts")
        if title is None or part is None:
            continue
        try:
            title_int = int(title)
        except (TypeError, ValueError):
            continue
        part_str = str(part).strip()
        if not part_str:
            continue
        out.append((fr_num, str(title_int), part_str))
    return out


def to_date(value: Any) -> Optional[str]:
    """
    Return a YYYY-MM-DD string or None. We let Postgres cast from text to DATE.
    """
    if not value:
        return None
    s = str(value)
    # Most FR dates are already YYYY-MM-DD, but strip time if present.
    if "T" in s:
        s = s.split("T", 1)[0]
    return s


def to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).lower()
    if s in ("true", "t", "1", "yes", "y"):
        return True
    if s in ("false", "f", "0", "no", "n"):
        return False
    return None


def ensure_jsonb_support() -> None:
    # Make sure psycopg2 knows how to adapt Python lists/dicts nicely,
    # though for TEXT[] we rely on default list adaptation.
    register_default_jsonb(loads=json.loads, globally=True)


def upsert_federal_register_documents(cur, doc: Dict[str, Any]) -> None:
    agency_id, agency_names = extract_agency_fields(doc)
    topics = doc.get("topics") or []
    reg_ids = doc.get("regulation_id_numbers") or []
    row = {
        "document_number": str(doc.get("document_number") or "").strip(),
        "document_id": None,  # can be backfilled from regs.gov later
        "document_title": doc.get("title"),
        "document_type": doc.get("type"),
        "abstract": doc.get("abstract"),
        "publication_date": to_date(doc.get("publication_date")),
        "effective_on": to_date(doc.get("effective_on")),
        "docket_ids": doc.get("docket_ids") or [],
        "agency_id": agency_id,
        "agency_names": agency_names,
        "topics": topics,
        "significant": to_bool(doc.get("significant")),
        "regulation_id_numbers": reg_ids,
        "html_url": doc.get("html_url"),
        "pdf_url": doc.get("pdf_url"),
        "json_url": doc.get("json_url"),
        "start_page": doc.get("start_page"),
        "end_page": doc.get("end_page"),
    }
    if not row["document_number"]:
        raise SystemExit("FR JSON is missing document_number; cannot ingest.")

    sql = """
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
    VALUES (
        %(document_number)s,
        %(document_id)s,
        %(document_title)s,
        %(document_type)s,
        %(abstract)s,
        %(publication_date)s,
        %(effective_on)s,
        %(docket_ids)s,
        %(agency_id)s,
        %(agency_names)s,
        %(topics)s,
        %(significant)s,
        %(regulation_id_numbers)s,
        %(html_url)s,
        %(pdf_url)s,
        %(json_url)s,
        %(start_page)s,
        %(end_page)s
    )
    ON CONFLICT (document_number) DO UPDATE SET
        document_id = EXCLUDED.document_id,
        document_title = EXCLUDED.document_title,
        document_type = EXCLUDED.document_type,
        abstract = EXCLUDED.abstract,
        publication_date = EXCLUDED.publication_date,
        effective_on = EXCLUDED.effective_on,
        docket_ids = EXCLUDED.docket_ids,
        agency_id = EXCLUDED.agency_id,
        agency_names = EXCLUDED.agency_names,
        topics = EXCLUDED.topics,
        significant = EXCLUDED.significant,
        regulation_id_numbers = EXCLUDED.regulation_id_numbers,
        html_url = EXCLUDED.html_url,
        pdf_url = EXCLUDED.pdf_url,
        json_url = EXCLUDED.json_url,
        start_page = EXCLUDED.start_page,
        end_page = EXCLUDED.end_page
    ;
    """
    cur.execute(sql, row)


def upsert_cfrparts(cur, rows: Iterable[Tuple[str, str, str]]) -> int:
    """
    Insert CFR parts derived from FR cfr_references into cfrparts.
    Uses ON CONFLICT DO NOTHING to avoid duplicates.
    """
    rows = list(rows)
    if not rows:
        return 0
    sql = """
    INSERT INTO cfrparts (frdocnum, title, cfrpart)
    VALUES (%s, %s, %s)
    ON CONFLICT (frdocnum, title, cfrpart) DO NOTHING;
    """
    cur.executemany(sql, rows)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest a Federal Register JSON document into Postgres.")
    ap.add_argument(
        "--json",
        required=True,
        help="Path to a Federal Register JSON file (as saved by download_fr_documents.py or agency_year_pipeline).",
    )
    args = ap.parse_args()

    path = Path(args.json)
    if not path.is_file():
        print(f"FR JSON not found: {path}", file=sys.stderr)
        return 1

    doc = load_fr_json(path)
    ensure_jsonb_support()

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                upsert_federal_register_documents(cur, doc)
                cfr_rows = extract_cfrparts(doc)
                inserted = upsert_cfrparts(cur, cfr_rows)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "document_number": doc.get("document_number"),
                    "cfrparts_rows_attempted": len(cfr_rows),
                    "cfrparts_rows_inserted": inserted,
                }
            )
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

