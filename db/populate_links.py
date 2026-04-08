#!/usr/bin/env python3
"""
Populate the links table with every CFR title/part pairing from ecfr.gov.

Fetches the full structure for each title from the eCFR versioner API, walks
the tree to find every part node (recording its full ancestor path), builds
the canonical ecfr.gov URL, and inserts into the links table.

Usage:
    python populate_links.py              # populate all titles
    python populate_links.py --dry-run    # print rows without writing to DB
    python populate_links.py --title 42   # process a single title (good for testing)

Environment variables:
    DB_HOST       database host          (default: localhost)
    DB_PORT       database port          (default: 5432)
    DB_NAME       database name          (default: mirrulations)
    DB_USER       database user          (default: postgres; local Mac/Homebrew often has no
                                         postgres role — use export DB_USER="$(whoami)")
    DB_PASSWORD   database password      (default: empty)
    DB_SSL        enable SSL, set to 1   (default: 0 — off for local dev)
    DB_SSLCERT    path to RDS CA bundle  (default: /certs/global-bundle.pem)
"""

import argparse
import datetime
import logging
import os
import sys

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── eCFR API ──────────────────────────────────────────────────────────────────

ECFR_BASE     = "https://www.ecfr.gov"
TITLES_URL    = f"{ECFR_BASE}/api/versioner/v1/titles.json"
STRUCTURE_URL = f"{ECFR_BASE}/api/versioner/v1/structure/{{date}}/title-{{title}}.json"
CURRENT_URL   = f"{ECFR_BASE}/current"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})

# ── DB config ─────────────────────────────────────────────────────────────────

_use_ssl  = os.environ.get("DB_SSL", "0").lower() in ("1", "true", "yes", "on")
_ssl_cert = os.environ.get("DB_SSLCERT", "/certs/global-bundle.pem")

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 5432)),
    "dbname":   os.environ.get("DB_NAME", "mirrulations"),
    # Fixes FATAL: role "postgres" does not exist on many local installs (see DB_USER in docstring).
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

if _use_ssl:
    DB_CONFIG["sslmode"]     = "verify-full"
    DB_CONFIG["sslrootcert"] = _ssl_cert


# ── eCFR helpers ──────────────────────────────────────────────────────────────

def fetch_titles() -> list:
    """Return all title objects from the eCFR titles endpoint."""
    log.info("Fetching title list from eCFR...")
    resp = SESSION.get(TITLES_URL, timeout=30)
    resp.raise_for_status()
    titles = resp.json().get("titles", [])
    log.info("  %d titles found", len(titles))
    return titles


def fetch_structure(title_number, date: str) -> dict:
    """Return the full structure JSON for one title on the given date."""
    url = STRUCTURE_URL.format(date=date, title=title_number)
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


# Node types we include as path segments when building the URL.
# "part" is where we stop and record the row — it is not added to the path
# because it becomes the leaf in the URL itself.
SEGMENT_TYPES = {"title", "chapter", "subchapter"}


def extract_parts(node: dict, ancestor_segments: list) -> list:
    """
    Recursively walk a structure tree node.

    Returns a list of (part_number, full_url) tuples — one per part node.
    ancestor_segments carries the URL path built so far (e.g.
    ["title-42", "chapter-IV", "subchapter-B"]).
    """
    node_type  = node.get("type", "")
    identifier = node.get("identifier", "")
    reserved   = node.get("reserved", False)

    # Build the URL segment for this node (if it contributes to the path)
    type_prefixes = {
        "title":      "title",
        "chapter":    "chapter",
        "subchapter": "subchapter",
    }
    prefix = type_prefixes.get(node_type)
    current_segments = ancestor_segments + ([f"{prefix}-{identifier}"] if prefix and identifier else [])

    results = []

    if node_type == "part" and identifier and not reserved:
        # Build the full URL: current ancestor path + this part slug
        part_slug = f"part-{identifier}"
        url = f"{CURRENT_URL}/{'/'.join(current_segments)}/{part_slug}?toc=1"
        results.append((str(identifier), url))

    for child in node.get("children", []):
        results.extend(extract_parts(child, current_segments))

    return results


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def upsert_links(conn, rows: list) -> tuple:
    """
    Insert (title, cfrpart, link) rows into the links table.
    Skips rows that conflict on any unique constraint (primary key OR link column).
    Returns (inserted, skipped) counts.
    """
    # ON CONFLICT DO NOTHING (no constraint specified) handles ALL unique violations —
    # both the PRIMARY KEY (title, cfrpart) and the UNIQUE constraint on link.
    # Specifying only ON CONFLICT (title, cfrpart) would leave the link UNIQUE
    # constraint unhandled, causing psycopg2 to raise an IntegrityError that aborts
    # the entire transaction.
    sql = """
        INSERT INTO links (title, cfrpart, link)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING;
    """
    inserted = 0
    skipped  = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute(sql, row)
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
            except psycopg2.IntegrityError as exc:
                # Shouldn't happen with ON CONFLICT DO NOTHING, but log and recover.
                log.warning("  Skipping row %s — integrity error: %s", row, exc)
                conn.rollback()
    conn.commit()
    return inserted, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Populate links table from ecfr.gov")
    p.add_argument("--dry-run", action="store_true",
                   help="Print rows without writing to the database")
    p.add_argument("--title", type=int, metavar="N",
                   help="Process a single title number (useful for testing)")
    return p.parse_args()


def main():
    args  = parse_args()
    today = datetime.date.today().isoformat()

    # 1. Fetch the list of all titles
    titles = fetch_titles()

    if args.title:
        titles = [t for t in titles if str(t.get("number")) == str(args.title)]
        if not titles:
            log.error("Title %d not found.", args.title)
            sys.exit(1)

    # 2. Connect to the database (skip if dry-run)
    conn = None
    if not args.dry_run:
        log.info("Connecting to %s:%s/%s...",
                 DB_CONFIG["host"], DB_CONFIG["port"], DB_CONFIG["dbname"])
        try:
            conn = get_connection()
            log.info("Connected.")
        except psycopg2.OperationalError as exc:
            log.error("DB connection failed: %s", exc)
            sys.exit(1)

    total_inserted = 0
    total_skipped  = 0

    for title_obj in titles:
        title_number = title_obj.get("number")
        if not title_number:
            continue

        # Use the title's latest amendment date so the structure is current
        date = title_obj.get("latest_amended_on") or today

        log.info("Processing Title %s (date: %s)...", title_number, date)

        try:
            structure = fetch_structure(title_number, date)
        except requests.HTTPError as exc:
            log.warning("  Skipping title %s — HTTP %s",
                        title_number, exc.response.status_code)
            continue

        parts = extract_parts(structure, [])
        log.info("  %d parts found", len(parts))

        if not parts:
            continue

        rows = [(str(title_number), part_number, url) for part_number, url in parts]

        if args.dry_run:
            for title_val, cfrpart_val, link_val in rows:
                print(f"  title={title_val:<4} cfrpart={cfrpart_val:<6} {link_val}")
            total_inserted += len(rows)
        else:
            inserted, skipped = upsert_links(conn, rows)
            total_inserted += inserted
            total_skipped  += skipped
            log.info("  Inserted %d, skipped %d (already exist)", inserted, skipped)

    if conn:
        conn.close()

    if args.dry_run:
        log.info("Dry run complete — %d rows would be inserted.", total_inserted)
    else:
        log.info("Done. Inserted: %d  Skipped: %d", total_inserted, total_skipped)


if __name__ == "__main__":
    main()
