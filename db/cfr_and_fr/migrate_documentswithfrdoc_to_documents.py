#!/usr/bin/env python3
"""
Migrate data from `documentswithfrdoc` → `documents`.

Default mode (merge): add any missing columns on `documents`, then bulk-upsert
shared columns from `documentswithfrdoc` (keeps extra rows on `documents` that
are not in the source).

``--replace-table``: drop ``public.documents`` (CASCADE), recreate it as a
structural copy of ``public.documentswithfrdoc`` (LIKE … INCLUDING ALL), then
``INSERT … SELECT *``. ``documentswithfrdoc`` is never dropped.

Connection: if ``USE_AWS_SECRETS`` is true (after loading ``--env-file``), reads
``AWS_REGION`` (or ``AWS_DEFAULT_REGION``) and ``AWS_SECRET_NAME`` and uses the
same JSON keys as the app: ``host``, ``port``, ``db`` (or ``dbname``),
``username``, ``password``. Otherwise uses ``DB_HOST``, ``DB_NAME``, etc.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def _use_aws_secrets() -> bool:
    return (os.getenv("USE_AWS_SECRETS", "").strip().lower() in {"1", "true", "yes", "on"})

EXTRA_COL_DEFS = [
    # Columns present on documentswithfrdoc but sometimes missing on documents
    # (types match db/schema-postgres.sql)
    ("frdocnum", "VARCHAR(50)"),
    ("attachments_self_link", "TEXT"),
    ("attachments_related_link", "TEXT"),
    ("file_formats", "JSONB"),
    ("display_properties", "JSONB"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Copy documentswithfrdoc → documents: merge (upsert) by default, "
            "or --replace-table to drop documents and recreate from source."
        )
    )
    p.add_argument("--env-file", default=".env", help="Path to .env (default: .env)")
    p.add_argument("--sslmode", default=None, help="Override sslmode (e.g. require, verify-full)")
    p.add_argument(
        "--sslrootcert",
        default=None,
        help="Path to CA bundle (used with sslmode=verify-full)",
    )
    p.add_argument(
        "--replace-table",
        action="store_true",
        help=(
            "Drop public.documents (CASCADE), recreate as LIKE documentswithfrdoc "
            "INCLUDING ALL, INSERT SELECT *. Destructive; FKs to documents are dropped."
        ),
    )
    p.add_argument("--dry-run", action="store_true", help="Print planned actions only.")
    return p.parse_args()


def connect(env_file: str, sslmode: str | None, sslrootcert: str | None):
    load_dotenv(Path(env_file))

    if _use_aws_secrets():
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit(
                "USE_AWS_SECRETS is set but boto3 is not installed. "
                "Install requirements or run: pip install boto3"
            ) from exc
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise SystemExit("USE_AWS_SECRETS requires AWS_REGION (or AWS_DEFAULT_REGION) in the environment.")
        secret_id = os.environ.get("AWS_SECRET_NAME")
        if not secret_id:
            raise SystemExit("USE_AWS_SECRETS requires AWS_SECRET_NAME in the environment.")
        client = boto3.client("secretsmanager", region_name=region)
        creds = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
        dbname = creds.get("db") or creds.get("dbname")
        if not dbname:
            raise SystemExit("Secret JSON must include a database name in key 'db' or 'dbname'.")
        host = creds["host"]
        port = int(creds.get("port", 5432))
        kw = dict(
            host=host,
            port=port,
            dbname=dbname,
            user=creds["username"],
            password=creds["password"],
        )
    else:
        host = os.environ["DB_HOST"]
        kw = dict(
            host=host,
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )

    # Default for RDS: require TLS unless overridden
    if sslmode:
        kw["sslmode"] = sslmode
    elif os.environ.get("PGSSLMODE"):
        kw["sslmode"] = os.environ["PGSSLMODE"]
    elif ".rds.amazonaws.com" in host:
        kw["sslmode"] = "require"

    if sslrootcert:
        kw["sslrootcert"] = sslrootcert
    elif os.environ.get("PGSSLROOTCERT"):
        kw["sslrootcert"] = os.environ["PGSSLROOTCERT"]

    return psycopg2.connect(**kw)


def regclass(cur, name: str) -> str | None:
    cur.execute("SELECT to_regclass(%s)", (name,))
    return cur.fetchone()[0]


def existing_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return {r[0] for r in cur.fetchall()}


def run_replace_table(cur, dry_run: bool) -> None:
    """Drop documents, recreate as copy of documentswithfrdoc schema + data."""
    if regclass(cur, "public.documentswithfrdoc") is None:
        raise SystemExit("Missing table public.documentswithfrdoc")

    stmts = []
    if regclass(cur, "public.documents") is not None:
        stmts.append("DROP TABLE public.documents CASCADE;")
    stmts.append(
        "CREATE TABLE public.documents (LIKE public.documentswithfrdoc INCLUDING ALL);"
    )
    stmts.append("INSERT INTO public.documents SELECT * FROM public.documentswithfrdoc;")

    if dry_run:
        print("Would run (replace-table):")
        for s in stmts:
            print(s)
        return

    for s in stmts:
        cur.execute(s)
    cur.execute("SELECT COUNT(*) FROM public.documents;")
    n_doc = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM public.documentswithfrdoc;")
    n_src = cur.fetchone()[0]
    print(f"Done. documents row count = {n_doc}, documentswithfrdoc row count = {n_src}.")


def run_merge(cur, dry_run: bool) -> None:
    """Add missing columns on documents, then upsert shared columns from documentswithfrdoc."""
    if regclass(cur, "public.documents") is None:
        raise SystemExit("Missing table public.documents")
    if regclass(cur, "public.documentswithfrdoc") is None:
        raise SystemExit("Missing table public.documentswithfrdoc")

    doc_cols = existing_columns(cur, "documents")
    docw_cols = existing_columns(cur, "documentswithfrdoc")

    # 1) Add missing "new" columns to documents
    alters: list[str] = []
    for col, coltype in EXTRA_COL_DEFS:
        if col in docw_cols and col not in doc_cols:
            alters.append(f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col} {coltype};")

    if alters:
        if dry_run:
            print("Would run ALTERs:")
            for stmt in alters:
                print(stmt)
        else:
            for stmt in alters:
                cur.execute(stmt)
            print(f"Added/verified {len(alters)} extra column(s) on documents.")
    else:
        print("No schema changes needed on documents.")

    doc_cols = existing_columns(cur, "documents")
    docw_cols = existing_columns(cur, "documentswithfrdoc")

    # 2) Bulk upsert all shared columns (including newly added)
    common = sorted((doc_cols & docw_cols) - {"id"})
    if "document_id" not in common:
        raise SystemExit("Expected shared primary key column document_id.")

    insert_cols = ", ".join(common)
    select_cols = ", ".join(common)

    update_cols = [c for c in common if c != "document_id"]
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    upsert_sql = f"""
        INSERT INTO documents ({insert_cols})
        SELECT {select_cols}
        FROM documentswithfrdoc
        ON CONFLICT (document_id) DO UPDATE
        SET {update_set}
    """

    if dry_run:
        print("\nWould run UPSERT SQL:")
        print(upsert_sql)
        return

    print("Starting UPSERT (this can take a while on millions of rows)...")
    cur.execute(upsert_sql)
    print("Done. documents now contains/upserts all documentswithfrdoc rows.")


def main() -> None:
    args = parse_args()
    conn = connect(args.env_file, args.sslmode, args.sslrootcert)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            if args.replace_table:
                run_replace_table(cur, args.dry_run)
            else:
                run_merge(cur, args.dry_run)
            if not args.dry_run:
                conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
