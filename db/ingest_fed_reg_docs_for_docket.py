#!/usr/bin/env python3
"""
Pipeline:
- Download docket from S3 via mirrulations-fetch
- Extract FR doc numbers from documents/*.json
- Fetch each FR document from the Federal Register API
- Ingest each into Postgres via ingest_federal_registry_document.py

Usage:
  python db/ingest_fed_reg_docs_for_docket.py --docket-id OSHA-2025-0005

Requires mirrulations-fetch to be installed:
  pip install -e /path/to/mirrulations-fetch
"""

import argparse
import json
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Set

import certifi

FR_API_URL = "https://www.federalregister.gov/api/v1/documents/{}.json"


# ─── Download docket from S3 ─────────────────────────────────────────────────

def download_docket(docket_id: str, output_dir: Path) -> Path:
    if shutil.which("mirrulations-fetch") is None:
        raise SystemExit(
            "mirrulations-fetch not found. Install it with:\n"
            "  pip install -e /path/to/mirrulations-fetch"
        )

    print(f"Downloading docket {docket_id} from S3...")
    cmd = [
        "mirrulations-fetch",
        docket_id,
        "--output-folder", str(output_dir),
        "--no-comments",
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        raise SystemExit(f"mirrulations-fetch failed for docket {docket_id}")

    docket_dir = output_dir / docket_id / "raw-data"
    if not docket_dir.exists():
        raise SystemExit(f"Expected download output not found: {docket_dir}")

    return docket_dir


# ─── Extract FR doc numbers ───────────────────────────────────────────────────

def extract_frdocnums(doc_path: Path) -> Set[str]:
    try:
        raw = json.loads(doc_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    fr_nums = set()

    # Navigate to attributes safely
    attrs = (
        raw.get("data", {})
           .get("attributes", {})
    )

    if not isinstance(attrs, dict):
        return fr_nums

    val = attrs.get("frDocNum")

    if isinstance(val, str) and val.strip():
        fr_nums.add(val.strip())

    return fr_nums


def collect_frdocnums(docket_dir: Path) -> Set[str]:
    docs_dir = docket_dir / "documents"

    if not docs_dir.exists():
        raise SystemExit(f"documents folder not found: {docs_dir}")

    all_nums = set()

    for file in docs_dir.glob("*.json"):
        nums = extract_frdocnums(file)
        all_nums.update(nums)

    return all_nums


# ─── Fetch from Federal Register API ─────────────────────────────────────────

def fetch_fr_document(frdocnum: str) -> dict:
    url = FR_API_URL.format(frdocnum)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(url, timeout=30, context=ssl_ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Not found in Federal Register API: {frdocnum}")
        else:
            print(f"HTTP {e.code} fetching {frdocnum}: {e.reason}")
        return {}
    except urllib.error.URLError as e:
        print(f"Network error fetching {frdocnum}: {e.reason}")
        return {}


# ─── Run ingest script ────────────────────────────────────────────────────────

def run_ingest(frdocnum: str):
    doc = fetch_fr_document(frdocnum)
    if not doc:
        return

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(doc, tmp)
        tmp_path = tmp.name

    cmd = [
        "python3",
        "db/ingest_federal_registry_document.py",
        "--json",
        tmp_path,
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"Ingested {frdocnum}")
    except subprocess.CalledProcessError:
        print(f"Failed ingest: {frdocnum}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--docket-id",
        required=True,
        help="Regulations.gov docket ID, e.g. OSHA-2025-0005",
    )
    args = ap.parse_args()

    output_dir = Path.cwd()
    docket_dir = download_docket(args.docket_id, output_dir)

    print("Collecting FR document numbers...")
    frdocnums = collect_frdocnums(docket_dir)

    print(f"Found {len(frdocnums)} unique FR documents")

    for frdocnum in sorted(frdocnums):
        run_ingest(frdocnum)


if __name__ == "__main__":
    main()