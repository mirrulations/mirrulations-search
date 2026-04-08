# Ingesting Federal Register Documents for a Docket

## Prerequisites

### 1. Set up a virtual environment

From the repo root, create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This ensures the correct Python and SSL certificates are used. You only need to do this once.

To activate the virtual environment in future sessions:

```bash
source .venv/bin/activate
```

### 2. Install mirrulations-fetch

`mirrulations-fetch` is a local package — install it in editable mode from its repo:

```bash
pip install -e /path/to/mirrulations-fetch
```

This only needs to be done once per virtual environment.

### 3. Set up the database

Your Postgres database must be running and reachable. The script reads connection info from a `.env` file or the standard `DATABASE_URL` / `PG*` environment variables. See `ingest_federal_registry_document.py` for details.

The `federal_register_documents` and `cfrparts` tables must exist. Run the schema if you haven't already:

Check if @DATABASE_URL is set: 
```bash
echo $DATABASE_URL
```

If emptry, set the @DATABASE_URL environment variable:

```bash
export DATABASE_URL=postgresql://localhost/mirrulations
```

Then run:
```bash
psql $DATABASE_URL -f db/schema-postgres.sql
```

## Usage

With the virtual environment active, run from the repo root:

```bash
python3 db/ingest_fed_reg_docs_for_docket.py --docket-id OSHA-2025-0005
```

Replace `OSHA-2025-0005` with any valid regulations.gov docket ID.

## What the script does

1. Calls `mirrulations-fetch <docket-id> --no-comments` to download the docket from the mirrulations S3 bucket into `./<docket-id>/raw-data/`
2. Reads each `raw-data/documents/*.json` file and extracts the `frDocNum` field
3. For each unique FR document number, fetches the full document JSON from the Federal Register API (`federalregister.gov/api/v1/documents/<frDocNum>.json`)
4. Ingests each document into Postgres — populating the `federal_register_documents` and `cfrparts` tables

## Notes

- The downloaded docket folder (e.g. `./OSHA-2025-0005/`) is left in the current directory after the script finishes and can be deleted manually.
- The script can be run against an empty database — `federal_register_documents` and `cfrparts` have no foreign key dependencies on other tables.
- Documents not found in the Federal Register API are skipped with a warning and do not cause the script to fail.
- Running the script more than once for the same docket is safe — inserts use `ON CONFLICT ... DO UPDATE` / `DO NOTHING`.
