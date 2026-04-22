#!/usr/bin/env python3
"""
Fetch docket data using mirrulations-fetch and ingest it into PostgreSQL.

This script combines mirrulations-fetch (to download docket data) with the
ingest_docket module to load data into the database. Optionally ingests full
Federal Register documents (API → federal_register_documents / cfrparts) using
``frDocNum`` values from regulations.gov document JSON. Derived PDF attachment
text under ``derived-data/.../extracted_txt`` is indexed into OpenSearch
``comments_extracted_text`` (not the ``documents`` index). Comment JSON under
``raw-data/comments/*.json`` is indexed into OpenSearch ``comments`` (same shape as
``ingest_opensearch.py``).

Usage:
    python db/ingest.py FAA-2025-0618
    python db/ingest.py --help

See ``db/INGEST.md`` for prerequisites, flags, and outputs.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import ssl
import sys
import subprocess
import time
import itertools
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tqdm import tqdm

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment]

# Allow `python db/ingest.py` from repo root without PYTHONPATH.
_ROOT = Path(__file__).resolve().parent.parent
_src = _ROOT / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from mirrsearch.db import get_opensearch_connection

from ingest_docket import (
    ingest_docket_and_documents,
    ingest_comments,
    extract_comment,
    load_raw_json,
    _ingest_summary,
    _require_ingest_schema,
    _ensure_comments_document_fk,
)

from ingest_federal_registry_document import (
    ensure_jsonb_support,
    upsert_federal_register_documents,
    extract_cfrparts,
    upsert_cfrparts,
)

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    """Configure logging verbosity.
    
    If verbose=False (default), suppress verbose HTTP request logs from opensearch and urllib3.
    If verbose=True, show all logs including detailed HTTP requests.
    """
    if not verbose:
        logging.getLogger("opensearch").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

FR_API_URL = "https://www.federalregister.gov/api/v1/documents/{}.json"

_REQUIRED_FR_TABLES = frozenset({"federal_register_documents", "cfrparts"})

OPENSEARCH_DOCUMENTS_INDEX = "documents_text"

DOCUMENTS_INDEX_BODY: dict[str, Any] = {
    "mappings": {
        "properties": {
            "docketId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "documentId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "documentText": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    }
}

OPENSEARCH_COMMENTS_INDEX = "comments"

COMMENTS_INDEX_BODY: dict[str, Any] = {
    "mappings": {
        "properties": {
            "commentId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "commentText": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "docketId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    }
}

OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX = "comments_extracted_text"

COMMENTS_EXTRACTED_TEXT_INDEX_BODY: dict[str, Any] = {
    "mappings": {
        "properties": {
            "attachmentId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "commentId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "docketId": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "extractedMethod": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "extractedText": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    }
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch docket data using mirrulations-fetch and ingest into PostgreSQL."
    )
    parser.add_argument(
        "docket_id",
        help="Docket ID (e.g., FAA-2025-0618)",
    )
    parser.add_argument(
        "--output-dir",
        default="./db/dockets",
        help="Output directory for fetched data (default: ./db/dockets)",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip the fetch step (data already exists)",
    )
    parser.add_argument(
        "--skip-comments-ingest",
        action="store_true",
        help="Skip ingesting comments",
    )
    parser.add_argument(
        "--skip-federal-register",
        action="store_true",
        help="Skip Federal Register API fetch and federal_register_documents / cfrparts ingest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run — validate data without writing to database",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)",
    )
    parser.add_argument(
        "--dbname",
        default="mirrulations",
        help="PostgreSQL database name (default: mirrulations)",
    )
    parser.add_argument(
        "--user",
        default="postgres",
        help="PostgreSQL user (default: postgres)",
    )
    parser.add_argument(
        "--password",
        help="PostgreSQL password",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (includes HTTP request details)",
    )
    return parser.parse_args()


def fetch_docket(docket_id: str, output_dir: str) -> Path:
    """Use mirrulations-fetch to download docket data."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    fetch_cmd = shutil.which("mirrulations-fetch")
    if not fetch_cmd:
        log.error(
            "mirrulations-fetch not found. "
            "Install it via: pip install mirrulations-fetch"
        )
        sys.exit(1)

    log.info(
        "Fetching docket data for %s using mirrulations-fetch...", docket_id
    )
    spinner = itertools.cycle(
        ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    )
    try:
        with subprocess.Popen(  # pylint: disable=consider-using-with
            [fetch_cmd, docket_id],
            cwd=output_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            while proc.poll() is None:
                sys.stdout.write(f"\r{next(spinner)}")
                sys.stdout.flush()
                time.sleep(0.1)
            sys.stdout.write("\r \r")
            sys.stdout.flush()

            if proc.returncode != 0:
                _, stderr = proc.communicate()
                log.error("Fetch failed: %s", stderr)
                sys.exit(1)

        docket_path = Path(output_dir) / docket_id
        if not docket_path.exists():
            log.error("Expected docket directory not found: %s", docket_path)
            sys.exit(1)
        return docket_path
    except FileNotFoundError as exc:
        log.error(
            "mirrulations-fetch not found. "
            "Install it via: pip install mirrulations-fetch"
        )
        raise SystemExit(1) from exc


def get_docket_ID(docket_dir: Path) -> str:
    """Return the docket ID string from a docket root directory path (folder name)."""
    return docket_dir.name


def get_document_ID(path: Path) -> str:
    """Return the document identifier used for indexing (file name)."""
    return path.name


def get_htm_files(docket_dir: Path) -> list[dict[str, Any]]:
    """
    Discover ``.htm`` / ``.html`` files under ``raw-data/documents/`` (recursive).
    Returns dicts with ``docketId``, ``documentId`` (file name), ``documentHtm`` (body text).
    If no HTM files found, extract document metadata from JSON files instead.
    """
    docs_dir = docket_dir / "raw-data" / "documents"
    if not docs_dir.is_dir():
        return []
    did = get_docket_ID(docket_dir)
    out: list[dict[str, Any]] = []
    
    # First, try to find HTM/HTML files
    for pattern in ("**/*.htm", "**/*.html"):
        for path in sorted(docs_dir.glob(pattern)):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("Could not read %s: %s", path, exc)
                continue
            out.append(
                {
                    "docketId": did,
                    "documentId": path.name,
                    "documentHtm": text,
                }
            )
    
    # If no HTM files found, extract metadata from JSON documents
    if not out:
        for json_path in sorted(docs_dir.glob("*.json")):
            if not json_path.is_file():
                continue
            try:
                payload = load_raw_json(json_path)
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Could not read or parse %s: %s", json_path, exc)
                continue
            
            if not isinstance(payload, dict):
                continue
            
            data = payload.get("data", {})
            if not isinstance(data, dict):
                continue
            
            doc_id = data.get("id")
            attrs = data.get("attributes", {})
            if not isinstance(attrs, dict):
                continue
            
            # Extract available text: title + abstract
            title = attrs.get("title", "")
            abstract = attrs.get("docAbstract", "")
            doc_text = f"{title}\n\n{abstract}" if title and abstract else (title or abstract or "")
            
            if not doc_text.strip():
                continue
            
            out.append(
                {
                    "docketId": did,
                    "documentId": doc_id or json_path.stem,
                    "documentHtm": doc_text,
                }
            )
    
    return out


def ensure_documents_index(client: Any) -> None:
    """Create the OpenSearch ``documents`` index if it does not exist."""
    if client.indices.exists(index=OPENSEARCH_DOCUMENTS_INDEX):
        return
    client.indices.create(index=OPENSEARCH_DOCUMENTS_INDEX, body=DOCUMENTS_INDEX_BODY)


def ingest_htm_files(docket_dir: Path, client: Any) -> int:
    """
    Index each discovered HTM/HTML file into OpenSearch (``documents`` index).
    Returns count ingested.
    """
    items = get_htm_files(docket_dir)
    if not items:
        log.info("No HTM/HTML files found in %s/raw-data/documents/", docket_dir.name)
        return 0
    
    ensure_documents_index(client)
    indexed = 0
    for item in tqdm(items, desc="Indexing documents to OpenSearch", unit="doc"):
        client.index(
            index=OPENSEARCH_DOCUMENTS_INDEX,
            id=item["documentId"],
            body={
                "docketId": item["docketId"],
                "documentId": item["documentId"],
                "documentText": item["documentHtm"],
            },
        )
        indexed += 1
    return indexed


def iter_comment_json_paths(docket_dir: Path) -> list[Path]:
    """Paths to ``*.json`` under ``raw-data/comments/`` (non-recursive)."""
    cdir = docket_dir / "raw-data" / "comments"
    if not cdir.is_dir():
        return []
    return sorted(p for p in cdir.glob("*.json") if p.is_file())


def _opensearch_comment_body(record: dict[str, Any]) -> dict[str, Any] | None:
    """Map ``extract_comment`` output to the OpenSearch ``comments`` document shape."""
    cid = record.get("comment_id")
    did = record.get("docket_id")
    if not cid or not did:
        return None
    raw = record.get("comment")
    if raw is None:
        text = ""
    elif isinstance(raw, str):
        text = raw
    else:
        text = str(raw)
    return {
        "commentId": str(cid),
        "docketId": str(did),
        "commentText": text,
    }


def ensure_comments_index(client: Any) -> None:
    """Create the OpenSearch ``comments`` index if it does not exist."""
    if client.indices.exists(index=OPENSEARCH_COMMENTS_INDEX):
        return
    client.indices.create(index=OPENSEARCH_COMMENTS_INDEX, body=COMMENTS_INDEX_BODY)


def ingest_comment_json_to_opensearch(docket_dir: Path, client: Any) -> int:
    """
    Index regulations.gov comment JSON from ``raw-data/comments/*.json`` into OpenSearch
    ``comments`` (``commentId``, ``commentText``, ``docketId``).
    """
    paths = iter_comment_json_paths(docket_dir)
    if not paths:
        return 0
    ensure_comments_index(client)
    indexed = 0
    for path in tqdm(paths, desc="Processing comments to OpenSearch", unit="comment"):
        payload = load_raw_json(path)
        if not isinstance(payload, dict):
            log.warning("Skipping %s — expected JSON object", path.name)
            continue
        data = payload.get("data")
        if not isinstance(data, dict):
            log.warning("Skipping %s — missing data object", path.name)
            continue
        record = extract_comment(data)
        body = _opensearch_comment_body(record)
        if not body:
            log.warning(
                "Skipping %s — missing comment_id or docket_id for OpenSearch",
                path.name,
            )
            continue
        client.index(
            index=OPENSEARCH_COMMENTS_INDEX,
            id=body["commentId"],
            body=body,
        )
        indexed += 1
    return indexed


def ensure_comments_extracted_text_index(client: Any) -> None:
    """Create the OpenSearch ``comments_extracted_text`` index if it does not exist."""
    if client.indices.exists(index=OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX):
        return
    client.indices.create(
        index=OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX,
        body=COMMENTS_EXTRACTED_TEXT_INDEX_BODY,
    )


def _normalized_comments_extracted_text_body(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Map a record from ``read_derived_extracted_text`` to the index document shape."""
    text = rec.get("extractedText") or rec.get("extracted_text")
    if not isinstance(text, str) or not text.strip():
        return None
    docket_id = rec.get("docketId") or rec.get("docket_id")
    comment_id = rec.get("commentId") or rec.get("comment_id")
    if not docket_id or not comment_id:
        return None
    attachment_id = rec.get("attachmentId") or rec.get("attachment_id")
    if not attachment_id:
        attachment_id = f"{comment_id}_attachment_1"
    method = rec.get("extractedMethod") or rec.get("extracted_method") or ""
    return {
        "docketId": str(docket_id),
        "commentId": str(comment_id),
        "attachmentId": str(attachment_id),
        "extractedMethod": str(method),
        "extractedText": text,
    }


def ingest_extracted_text_to_comments_extracted_text(
    client: Any, records: list[dict[str, Any]]
) -> int:
    """Index derived extracted-text records into OpenSearch ``comments_extracted_text``."""
    indexed = 0
    for rec in tqdm(records, desc="Indexing extracted text to OpenSearch", unit="text"):
        body = _normalized_comments_extracted_text_body(rec)
        if not body:
            continue
        client.index(
            index=OPENSEARCH_COMMENTS_EXTRACTED_TEXT_INDEX,
            id=body["attachmentId"],
            body=body,
        )
        indexed += 1
    return indexed


def document_content_html_paths(docket_dir: Path) -> list[tuple[str, Path]]:
    """
    Return (document_id, path) for each ``*_content.htm`` under ``raw-data/documents/``.

    Pairs with regulations.gov JSON exports named like ``<document_id>.json`` (e.g.
    ``FAA-2025-0618-0001_content.htm`` → document id ``FAA-2025-0618-0001``).
    """
    docs_dir = docket_dir / "raw-data" / "documents"
    if not docs_dir.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for path in sorted(docs_dir.glob("*_content.htm")):
        doc_id = path.name.removesuffix("_content.htm")
        if doc_id:
            out.append((doc_id, path))
    return out


def read_document_content_html(docket_dir: Path) -> dict[str, str]:
    """Read UTF-8 text from each ``*_content.htm`` file; map ``document_id`` → HTML body."""
    result: dict[str, str] = {}
    for doc_id, path in document_content_html_paths(docket_dir):
        try:
            result[doc_id] = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Could not read %s: %s", path, exc)
    return result


def extracted_txt_dir(docket_dir: Path) -> Path | None:
    """
    Resolve ``.../extracted_txt`` under ``derived-data`` if present.

    Tries, in order:

    - ``derived-data/mirrulations/extracted_txt`` (common local mirrulations-fetch layout)
    - ``derived-data/<agency>/<docket_id>/extracted_txt`` (S3-style; agency = segment before
      first ``-`` in the docket folder name)
    - Any ``derived-data/**/extracted_txt`` directory (first match)
    """
    candidates: list[Path] = [
        docket_dir / "derived-data" / "mirrulations" / "extracted_txt",
    ]
    did = docket_dir.name
    if "-" in did:
        agency = did.split("-", 1)[0]
        candidates.append(docket_dir / "derived-data" / agency / did / "extracted_txt")
    for p in candidates:
        if p.is_dir():
            return p
    derived = docket_dir / "derived-data"
    if derived.is_dir():
        for p in sorted(derived.rglob("extracted_txt")):
            if p.is_dir():
                return p
    return None


def iter_extracted_txt_json_files(docket_dir: Path) -> list[Path]:
    """Paths to ``*.json`` under the resolved ``extracted_txt`` tree (recursive)."""
    root = extracted_txt_dir(docket_dir)
    if not root:
        return []
    return sorted(p for p in root.rglob("*.json") if p.is_file())


_EXTRACTED_PLAIN_NAME = re.compile(
    r"^(?P<comment_id>.+)_attachment_(?P<attach>\d+)_extracted\.txt$",
    re.IGNORECASE,
)


def iter_extracted_plain_txt_files(docket_dir: Path) -> list[Path]:
    """
    Paths to ``*_extracted.txt`` under ``extracted_txt`` (e.g.
    ``.../extracted_txt/comments_extracted_text/pypdf/FAA-...-0007_attachment_1_extracted.txt``).
    """
    root = extracted_txt_dir(docket_dir)
    if not root:
        return []
    return sorted(p for p in root.rglob("*_extracted.txt") if p.is_file())


def read_derived_extracted_plain_text(docket_dir: Path) -> list[dict[str, Any]]:
    """
    Load plain-text extractions (PDF attachment text). Filenames must look like
    ``<commentId>_attachment_<n>_extracted.txt``. ``extractedMethod`` is taken from the
    parent directory name (e.g. ``pypdf``).
    """
    docket_id = docket_dir.name
    out: list[dict[str, Any]] = []
    files = iter_extracted_plain_txt_files(docket_dir)
    for path in tqdm(
        files,
        desc="Reading extracted plain text files",
        unit="file",
        disable=len(files) < 50,
    ):
        m = _EXTRACTED_PLAIN_NAME.match(path.name)
        if not m:
            log.warning(
                "Skipping %s (expected <commentId>_attachment_<n>_extracted.txt)",
                path,
            )
            continue
        comment_id = m.group("comment_id")
        attach_n = int(m.group("attach"))
        method = path.parent.name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Could not read %s: %s", path, exc)
            continue
        out.append(
            {
                "docketId": docket_id,
                "commentId": comment_id,
                "attachmentId": f"{comment_id}_attachment_{attach_n}",
                "extractedMethod": method,
                "extractedText": text,
            }
        )
    return out


def read_derived_extracted_text(docket_dir: Path) -> list[dict[str, Any]]:
    """
    Load extracted comment-attachment text from ``derived-data/.../extracted_txt``:

    - ``*.json`` — one object or a JSON array per file
    - ``*_extracted.txt`` — plain text (e.g. under ``comments_extracted_text/pypdf/``)
    """
    records: list[dict[str, Any]] = []
    json_files = iter_extracted_txt_json_files(docket_dir)
    for path in tqdm(
        json_files,
        desc="Reading extracted JSON files",
        unit="file",
        disable=len(json_files) < 50,
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read or parse %s: %s", path, exc)
            continue
        if isinstance(data, dict):
            records.append(data)
        elif isinstance(data, list):
            records.extend(x for x in data if isinstance(x, dict))
    records.extend(read_derived_extracted_plain_text(docket_dir))
    return records


# ─── Federal Register (same pipeline as ingest_fed_reg_docs_for_docket.py) ───


def extract_frdocnums_from_document_json(doc_path: Path) -> set[str]:
    """Read ``frDocNum`` from a regulations.gov v4 document JSON export."""
    try:
        raw = json.loads(doc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()

    attrs = raw.get("data", {})
    if not isinstance(attrs, dict):
        return set()
    attrs = attrs.get("attributes", {})
    if not isinstance(attrs, dict):
        return set()

    val = attrs.get("frDocNum")
    if isinstance(val, str) and val.strip():
        return {val.strip()}
    return set()


def collect_frdocnums_from_docket(docket_dir: Path) -> set[str]:
    """Collect unique ``frDocNum`` values from ``<docket>/raw-data/documents/*.json``."""
    docs_dir = docket_dir / "raw-data" / "documents"
    if not docs_dir.is_dir():
        return set()
    all_nums: set[str] = set()
    json_files = list(docs_dir.glob("*.json"))
    for path in tqdm(
        json_files,
        desc="Extracting frDocNum values",
        unit="doc",
        disable=len(json_files) < 20,
    ):
        all_nums.update(extract_frdocnums_from_document_json(path))
    return all_nums


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def fetch_fr_document(frdocnum: str) -> dict[str, Any]:
    """GET Federal Register API JSON for ``frdocnum``; return ``{}`` on 404 or error."""
    url = FR_API_URL.format(frdocnum)
    try:
        with urllib.request.urlopen(url, timeout=30, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("Not found in Federal Register API: %s", frdocnum)
        else:
            log.warning("HTTP %s fetching %s: %s", e.code, frdocnum, e.reason)
        return {}
    except urllib.error.URLError as e:
        log.warning("Network error fetching %s: %s", frdocnum, e.reason)
        return {}


def _require_fr_schema(conn: Any, args: argparse.Namespace) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lower(table_name) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        have = {r[0] for r in cur.fetchall()}
    missing = sorted(_REQUIRED_FR_TABLES - have)
    if missing:
        log.error(
            "Database %r is missing Federal Register table(s): %s.\n"
            "Apply schema: psql -h %s -p %s -U %s -d %s -f db/schema-postgres.sql",
            args.dbname,
            ", ".join(missing),
            args.host,
            args.port,
            args.user,
            args.dbname,
        )
        sys.exit(1)


def ingest_federal_register_for_docket(
    docket_dir: Path,
    conn: Any,
    args: argparse.Namespace,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """
    For each unique ``frDocNum`` in ``raw-data/documents/*.json``, fetch FR API JSON and upsert
    into ``federal_register_documents`` and ``cfrparts``.

    Returns ``(ingested_count, skipped_count)`` where skipped includes 404s and fetch failures.
    """
    frdocnums = collect_frdocnums_from_docket(docket_dir)
    if not frdocnums:
        log.info("Federal Register: no frDocNum values in raw-data/documents — skipping.")
        return 0, 0

    if dry_run:
        log.info(
            "[DRY RUN] Federal Register: would fetch and ingest %d document(s): %s",
            len(frdocnums),
            ", ".join(sorted(frdocnums)),
        )
        return len(frdocnums), 0

    _require_fr_schema(conn, args)
    ensure_jsonb_support()

    ingested = 0
    skipped = 0
    for frdocnum in tqdm(
        sorted(frdocnums),
        desc="Fetching Federal Register documents",
        unit="doc",
        disable=len(frdocnums) < 5,
    ):
        doc = fetch_fr_document(frdocnum)
        if not doc:
            skipped += 1
            continue
        try:
            with conn.cursor() as cur:
                upsert_federal_register_documents(cur, doc)
                cfr_rows = extract_cfrparts(doc)
                upsert_cfrparts(cur, cfr_rows)
            conn.commit()
            ingested += 1
            if args.verbose:
                log.info("Federal Register: ingested %s", frdocnum)
        except Exception as exc:  # pylint: disable=broad-except
            conn.rollback()
            log.warning("Federal Register: failed to ingest %s: %s", frdocnum, exc)
            skipped += 1

    return ingested, skipped


def ingest_into_postgresql_dry_run(docket_dir: Path, args: argparse.Namespace) -> None:
    log.info("DRY RUN — no database writes.")
    ok, n_doc, sk, fetched_docket_id = ingest_docket_and_documents(
        docket_dir, conn=None, dry_run=True, verbose=args.verbose
    )
    pc, cs = (0, 0)
    if ok and not args.skip_comments_ingest:
        pc, cs = ingest_comments(
            docket_dir, conn=None, dry_run=True, verbose=args.verbose
        )
    fr_i, fr_sk = (0, 0)
    if ok and not args.skip_federal_register:
        fr_i, fr_sk = ingest_federal_register_for_docket(
            docket_dir, None, args, dry_run=True
        )
    if ok:
        if args.skip_comments_ingest:
            log.info("Documents: %d upserted", n_doc)
        else:
            log.info("Documents: %d upserted; Comments: %d processed", n_doc, pc)
        if not args.skip_federal_register:
            log.info(
                "Federal Register (dry run): %d would ingest, %d skipped",
                fr_i,
                fr_sk,
            )
        _ingest_summary(
            docket_dir,
            fetched_docket_id,
            None,
            dry_run=True,
            skip_comments_ingest=args.skip_comments_ingest,
            verbose=args.verbose,
        )
    else:
        sys.exit(1)


def ingest_into_postgresql(docket_dir: Path, args: argparse.Namespace) -> None:
    log.info("Connecting to PostgreSQL at %s:%d/%s…", args.host, args.port, args.dbname)
    try:
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password or None,
        )
    except psycopg2.OperationalError as exc:
        log.error("Could not connect to database: %s", exc)
        sys.exit(1)

    _require_ingest_schema(conn, args)
    _ensure_comments_document_fk(conn)

    try:
        ok, n_doc, sk, docket_id = ingest_docket_and_documents(
            docket_dir, conn, dry_run=False, verbose=args.verbose
        )
        pc, cs = (0, 0)
        if ok and not args.skip_comments_ingest:
            pc, cs = ingest_comments(docket_dir, conn, dry_run=False, verbose=args.verbose)
        fr_ing, fr_skip = (0, 0)
        if ok and not args.skip_federal_register:
            fr_ing, fr_skip = ingest_federal_register_for_docket(
                docket_dir, conn, args, dry_run=False
            )
        if ok:
            if args.skip_comments_ingest:
                log.info("Documents: %d upserted", n_doc)
            else:
                log.info("Documents: %d upserted; Comments: %d processed", n_doc, pc)
            if not args.skip_federal_register:
                log.info(
                    "Federal Register: %d ingested, %d skipped/failed",
                    fr_ing,
                    fr_skip,
                )
            _ingest_summary(
                docket_dir,
                docket_id,
                conn,
                dry_run=False,
                skip_comments_ingest=args.skip_comments_ingest,
                verbose=args.verbose,
            )
        else:
            sys.exit(1)
    finally:
        conn.close()


def main():
    if load_dotenv:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    args = parse_args()
    _configure_logging(args.verbose)
    docket_id = args.docket_id.strip().upper()

    if not args.skip_fetch:
        docket_dir = fetch_docket(docket_id, args.output_dir)
    else:
        docket_dir = Path(args.output_dir) / docket_id
        if not docket_dir.exists():
            log.error("Docket directory not found: %s (omit --skip-fetch to fetch)", docket_dir)
            sys.exit(1)
    # if not verbose, suppress noisy logs from HTTP requests in opensearch and urllib3
    if args.verbose:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("opensearch").setLevel(logging.WARNING)
        log.info("Using docket directory: %s", docket_dir)

    html_by_doc = read_document_content_html(docket_dir)
    if html_by_doc and args.verbose:
        log.info(
            "Read %d document HTML file(s): %s",
            len(html_by_doc),
            ", ".join(sorted(html_by_doc)),
        )

    extracted_records = read_derived_extracted_text(docket_dir)
    if extracted_records and args.verbose:
        log.info("Read %d derived extracted-text record(s)", len(extracted_records))

    if args.dry_run:
        ingest_into_postgresql_dry_run(docket_dir, args)
    else:
        ingest_into_postgresql(docket_dir, args)

    try:
        client = get_opensearch_connection()
        d_count = ingest_htm_files(docket_dir, client)
        c_count = 0
        if not args.skip_comments_ingest:
            c_count = ingest_comment_json_to_opensearch(docket_dir, client)
        if extracted_records:
            ensure_comments_extracted_text_index(client)
            ingest_extracted_text_to_comments_extracted_text(client, extracted_records)
        log.info(
            "OpenSearch ingest complete: %d document(s), %d comment(s), %d extracted text(s)",
            d_count,
            c_count,
            len(extracted_records),
        )
    except Exception as exc:
        log.error("OpenSearch ingest failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
