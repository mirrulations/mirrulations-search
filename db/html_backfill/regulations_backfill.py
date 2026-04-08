"""
regulations_backfill.py

Reads a docket_htm_status.txt report and targets only dockets marked [NO ]
(i.e. dockets that have no .htm files and therefore need .html files).

For each [NO] docket:
  1. Query the regulations.gov API for all documents in that docket
  2. For each document, check its fileList for .html files
  3. Download any .html files not already present locally

Local output path:
  ./output/{agency_id}/{docket_id}/text-{docket_id}/documents/{filename}.html

Usage:
  python regulations_backfill.py --input docket_htm_status.txt
  python regulations_backfill.py --input docket_htm_status.txt --dry-run
  python regulations_backfill.py --retry
"""

import requests
import json
import time
import csv
import sys
import os
import re
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv is not installed. Run: pip install python-dotenv")
    sys.exit(1)

# Load .env from same directory as this script
load_dotenv(Path(__file__).parent / ".env")

# ── Configuration ─────────────────────────────────────────────────────────────

API_KEY          = os.getenv("REGULATIONS_API_KEY", "")
BASE_URL         = "https://api.regulations.gov/v4"
OUTPUT_DIR       = Path("./output")
CHECKPOINT_FILE  = Path("./checkpoint.json")
FAILED_LOG       = Path("./failed.csv")
STATS_FILE       = Path("./stats.json")

HEADERS          = {"X-Api-Key": API_KEY}
RATE_LIMIT_DELAY = 3.7   # ~970 req/hr — safely under 1,000/hr cap
PAGE_SIZE        = 250   # max allowed by the API

# ── Stats tracker ─────────────────────────────────────────────────────────────

class Stats:
    def __init__(self):
        self.dockets_total    = 0
        self.dockets_done     = 0
        self.docs_scanned     = 0
        self.already_local    = 0
        self.html_downloaded  = 0
        self.no_html_in_api   = 0   # API had no .html for this doc
        self.failed           = 0
        self.start_time       = datetime.now()

    def summary(self):
        elapsed = datetime.now() - self.start_time
        hrs, rem = divmod(int(elapsed.total_seconds()), 3600)
        mins, secs = divmod(rem, 60)
        pct = (self.dockets_done / self.dockets_total * 100) if self.dockets_total else 0
        return (
            f"\n{'─' * 54}\n"
            f"  Elapsed           : {hrs:02d}h {mins:02d}m {secs:02d}s\n"
            f"  Dockets processed : {self.dockets_done:>10,} / {self.dockets_total:,} ({pct:.1f}%)\n"
            f"  Documents scanned : {self.docs_scanned:>10,}\n"
            f"  Already local     : {self.already_local:>10,}  (skipped)\n"
            f"  No .html in API   : {self.no_html_in_api:>10,}\n"
            f"  .html downloaded  : {self.html_downloaded:>10,}\n"
            f"  Failures          : {self.failed:>10,}\n"
            f"{'─' * 54}"
        )

    def save(self):
        STATS_FILE.write_text(json.dumps({
            "dockets_total":   self.dockets_total,
            "dockets_done":    self.dockets_done,
            "docs_scanned":    self.docs_scanned,
            "already_local":   self.already_local,
            "html_downloaded": self.html_downloaded,
            "no_html_in_api":  self.no_html_in_api,
            "failed":          self.failed,
        }, indent=2))

stats = Stats()

# ── Parse docket_htm_status.txt ───────────────────────────────────────────────

def parse_no_htm_dockets(filepath: Path) -> list[tuple[str, str]]:
    """
    Parse the report file and return a list of (agency_id, docket_id) tuples
    for every docket marked [NO ] — i.e. dockets with no .htm files that
    therefore need .html files backfilled.

    Docket IDs follow the pattern AGENCY-YYYY-NNNN, so agency_id is
    everything before the first hyphen-year segment.
    """
    dockets = []
    pattern = re.compile(r'\[NO \]\s+(\S+)')

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                docket_id = m.group(1)
                # Agency ID = everything up to the first -YYYY- segment
                agency_id = docket_id.split("-")[0]
                dockets.append((agency_id, docket_id))
    
    def sort_key(item):
        _, docket_id = item
        parts = docket_id.split("-")

        # Expect format: AGENCY-YYYY-NNNN
        try:
            year = int(parts[1])
            number = int(parts[2])
        except (IndexError, ValueError):
            # fallback for weird formats
            return (0, 0)

        return (year, number)
    
    dockets.sort(key=sort_key, reverse=True)  # Newest first
    return dockets

# ── Checkpoint helpers ────────────────────────────────────────────────────────

def load_checkpoint() -> set:
    """Returns a set of already-completed docket_ids."""
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        return set(data.get("completed_dockets", []))
    return set()

def save_checkpoint(completed: set):
    CHECKPOINT_FILE.write_text(json.dumps(
        {"completed_dockets": sorted(completed)}, indent=2
    ))

def log_failure(docket_id: str, doc_id: str, reason: str):
    stats.failed += 1
    with open(FAILED_LOG, "a", newline="") as f:
        csv.writer(f).writerow([docket_id, doc_id, reason])

# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path, params=None, retries=3):
    """GET with automatic retry and 429 back-off."""
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                print(f"  Rate limited — sleeping {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            print(f"  HTTP {resp.status_code} → {url}")
            return None
        except requests.RequestException as e:
            print(f"  Request error (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(5 * (attempt + 1))
    return None

def download_file(url: str, dest_path: Path, retries=3) -> bool:
    """Stream-download a file. Returns True on success."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=90, stream=True)
            if resp.status_code == 200:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            print(f"  HTTP {resp.status_code} downloading {dest_path.name}")
        except Exception as e:
            print(f"  Download error (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(3 * (attempt + 1))
    return False

# ── Destination path ──────────────────────────────────────────────────────────

def dest_path_for(agency_id: str, docket_id: str, file_name: str) -> Path:
    """
    ./output/{agency_id}/{docket_id}/text-{docket_id}/documents/{file_name}
    """
    return (
        OUTPUT_DIR
        / agency_id
        / docket_id
        / f"text-{docket_id}"
        / "documents"
        / file_name
    )

# ── Core logic ────────────────────────────────────────────────────────────────

def process_document(doc_id: str, agency_id: str, docket_id: str, dry_run: bool):
    """Check a document's fileList for .html files and download them."""
    stats.docs_scanned += 1

    data = api_get(f"/documents/{doc_id}")
    time.sleep(RATE_LIMIT_DELAY)

    if not data:
        log_failure(docket_id, doc_id, "API metadata fetch failed")
        return

    attrs     = data.get("data", {}).get("attributes", {})
    file_list = attrs.get("fileList", []) or []

    html_files = [
        f for f in file_list
        if f.get("fileName", "").lower().endswith(".html")
    ]

    if not html_files:
        stats.no_html_in_api += 1
        return

    for file_info in html_files:
        file_url  = file_info.get("fileUrl", "")
        file_name = file_info.get("fileName", "")
        if not file_url or not file_name:
            continue

        dest = dest_path_for(agency_id, docket_id, file_name)

        if dest.exists():
            stats.already_local += 1
            print(f"    Skipping {file_name} (already local)")
            continue

        if dry_run:
            print(f"    [DRY RUN] Would download {file_name}")
            stats.html_downloaded += 1
            continue

        print(f"    Downloading {file_name}")
        if download_file(file_url, dest):
            stats.html_downloaded += 1
        else:
            log_failure(docket_id, doc_id, f"download failed: {file_name}")


def process_docket(agency_id: str, docket_id: str, dry_run: bool):
    """Page through all documents in a docket and process each one."""
    page = 1

    while True:
        data = api_get("/documents", params={
            "filter[docketId]": docket_id,
            "page[size]":       PAGE_SIZE,
            "page[number]":     page,
        })
        time.sleep(RATE_LIMIT_DELAY)

        if not data:
            print(f"  No response for {docket_id} page {page}")
            break

        docs = data.get("data", [])
        if not docs:
            break

        for doc in docs:
            doc_id = doc.get("id")
            if doc_id:
                process_document(doc_id, agency_id, docket_id, dry_run)

        total_pages = data.get("meta", {}).get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1


def retry_failed():
    """Re-attempt every entry in failed.csv."""
    if not FAILED_LOG.exists():
        print("No failed.csv found — nothing to retry.")
        return

    with open(FAILED_LOG, newline="") as f:
        rows = list(csv.reader(f))

    if not rows:
        print("failed.csv is empty.")
        return

    print(f"Retrying {len(rows)} failed entries...")
    FAILED_LOG.unlink()

    for row in rows:
        if len(row) < 2:
            continue
        docket_id, doc_id = row[0], row[1]
        agency_id = docket_id.split("-")[0]
        print(f"  Retrying doc {doc_id} in {docket_id}")
        process_document(doc_id, agency_id, docket_id, dry_run=False)

    print(stats.summary())


def run(input_file: Path, dry_run: bool):
    """Main entry point."""
    if not API_KEY:
        print(
            "ERROR: REGULATIONS_API_KEY is not set.\n"
            "Create a .env file with:\n"
            "  REGULATIONS_API_KEY=your_key_here\n"
            "Get a free key at: https://api.data.gov/signup/"
        )
        sys.exit(1)

    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Parsing {input_file.name} for [NO ] dockets...")
    dockets = parse_no_htm_dockets(input_file)
    stats.dockets_total = len(dockets)
    print(f"Found {stats.dockets_total:,} dockets to backfill.\n")

    if dry_run:
        print("*** DRY RUN MODE — no files will be written ***\n")

    completed = load_checkpoint()

    for i, (agency_id, docket_id) in enumerate(dockets, 1):
        if docket_id in completed:
            stats.dockets_done += 1
            continue

        print(f"[{i:,}/{stats.dockets_total:,}] {docket_id}")
        process_docket(agency_id, docket_id, dry_run)

        stats.dockets_done += 1
        completed.add(docket_id)

        if not dry_run:
            save_checkpoint(completed)
            stats.save()

        # Print summary every 100 dockets
        if i % 100 == 0:
            print(stats.summary())

    print("\n✓ Backfill complete.")
    print(f"  Output    : {OUTPUT_DIR.resolve()}")
    print(f"  Checkpoint: {CHECKPOINT_FILE.resolve()}")
    if FAILED_LOG.exists():
        with open(FAILED_LOG) as f:
            n = sum(1 for _ in f)
        print(f"  Failures  : {n} (run --retry to re-attempt)")
    print(stats.summary())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("docket_htm_status.txt"),
        metavar="FILE",
        help="Path to docket_htm_status.txt (default: ./docket_htm_status.txt)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and scan the API but don't write any files."
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry all entries previously logged in failed.csv."
    )
    args = parser.parse_args()

    if args.retry:
        retry_failed()
    else:
        run(input_file=args.input, dry_run=args.dry_run)
