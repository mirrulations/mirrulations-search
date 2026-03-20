#!/usr/bin/env python3
"""
Populate links(title, cfrPart, link) with eCFR part URLs.

Flow:
1) Fetch CFR titles from:
   https://www.ecfr.gov/api/versioner/v1/titles.json
2) For each title, fetch structure from:
   https://www.ecfr.gov/api/versioner/v1/structure/current/title-{number}.json
3) Recursively collect nodes where type == "part" and read identifier.
4) Build URL:
   https://www.ecfr.gov/current/title-{title}/part-{part}?toc=1
5) Insert via ON CONFLICT (title, cfrPart) DO NOTHING.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import psycopg2
import requests
from dotenv import load_dotenv


TITLES_URL = "https://www.ecfr.gov/api/versioner/v1/titles.json"
STRUCTURE_URL_TEMPLATE = (
    "https://www.ecfr.gov/api/versioner/v1/structure/current/title-{title}.json"
)
PART_URL_TEMPLATE = "https://www.ecfr.gov/current/title-{title}/part-{part}?toc=1"
TIMEOUT_SECONDS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate links(title, cfrPart, link) "
            "from eCFR structure API."
        )
    )
    parser.add_argument(
        "--view",
        action="store_true",
        help=(
            "Show links row count and sample rows, "
            "then exit."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print what would be inserted "
            "without writing to DB."
        ),
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Sample row count for --view (default: 10).",
    )
    return parser.parse_args()


def load_environment() -> None:
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
    }


def fetch_titles() -> list[str]:
    response = requests.get(TITLES_URL, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    titles = payload.get("titles", [])
    result: list[str] = []
    if not isinstance(titles, list):
        return result

    for item in titles:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        if number is None:
            continue
        text = str(number).strip()
        if text:
            result.append(text)
    return result


def fetch_structure(title: str) -> dict[str, Any]:
    url = STRUCTURE_URL_TEMPLATE.format(title=title)
    response = requests.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def collect_parts(node: Any, parts: set[str]) -> None:
    if isinstance(node, dict):
        node_type = node.get("type")
        identifier = node.get("identifier")
        if node_type == "part" and identifier is not None:
            part = str(identifier).strip()
            if part:
                parts.add(part)

        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                collect_parts(child, parts)

    elif isinstance(node, list):
        for child in node:
            collect_parts(child, parts)


def build_link(title: str, part: str) -> str:
    return PART_URL_TEMPLATE.format(title=title, part=part)


def view_links(cur: Any, sample_limit: int) -> None:
    cur.execute("SELECT count(*) FROM links")
    total = cur.fetchone()[0]
    print(f"links row count: {total}")
    cur.execute(
        """
        SELECT title, cfrPart, link
        FROM links
        ORDER BY title, cfrPart
        LIMIT %s
        """,
        (sample_limit,),
    )
    rows = cur.fetchall()
    if not rows:
        print("No rows in links.")
        return
    print(f"Sample rows (limit {sample_limit}):")
    for title, cfr_part, link in rows:
        print(f"  title={title} part={cfr_part} link={link}")


def main() -> None:
    args = parse_args()
    load_environment()

    conn = psycopg2.connect(**db_config())
    try:
        with conn.cursor() as cur:
            if args.view:
                view_links(cur, args.sample_limit)
                return

            titles = fetch_titles()
            total_titles_processed = 0
            total_parts_found = 0
            total_rows_inserted = 0

            for title in titles:
                try:
                    structure = fetch_structure(title)
                except requests.RequestException as exc:
                    print(f"Title {title}: error fetching structure: {exc}")
                    continue

                parts: set[str] = set()
                collect_parts(structure, parts)
                sorted_parts = sorted(parts)
                inserted_for_title = 0

                if args.dry_run:
                    for part in sorted_parts:
                        print(
                            f"DRY RUN: title={title} part={part} "
                            f"link={build_link(title, part)}"
                        )
                    inserted_for_title = len(sorted_parts)
                else:
                    for part in sorted_parts:
                        link = build_link(title, part)
                        cur.execute(
                            """
                            INSERT INTO links (title, cfrPart, link)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (title, cfrPart) DO NOTHING
                            """,
                            (str(title), str(part), link),
                        )
                        if cur.rowcount > 0:
                            inserted_for_title += 1

                total_titles_processed += 1
                total_parts_found += len(sorted_parts)
                total_rows_inserted += inserted_for_title
                print(
                    f"Title {title}: found {len(sorted_parts)} parts, "
                    f"inserted {inserted_for_title} rows"
                )

            if not args.dry_run:
                conn.commit()

            print("Done.")
            print(f"Total titles processed: {total_titles_processed}")
            print(f"Total parts found: {total_parts_found}")
            print(f"Total rows inserted: {total_rows_inserted}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
