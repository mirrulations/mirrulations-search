# `ingest_federal_registry_document.py`
### Ingest one Federal Register JSON file → Postgres
This script ingests a **single** Federal Register (FR) document JSON file (as downloaded/saved from the Federal Register API) into the main Postgres database.
It is useful for:
- Backfilling one missing FR document without running a bulk pipeline
- Testing schema / data mapping on a single known FR document
---
## What it writes
The script **upserts** (insert or update) one row into:
- **`federal_register_documents`**: keyed by `document_number`
It also inserts **0+ rows** into:
- **`cfrparts`**: one row per CFR reference found in `cfr_references` (keyed by `(frdocnum, title, cfrpart)`)
The script prints a JSON status object like:
```json
{"status":"ok","document_number":"2025-21121","cfrparts_rows_attempted":0,"cfrparts_rows_inserted":0}
```
`cfrparts_rows_attempted` can be `0` if the FR JSON has no `cfr_references` (or they’re empty/malformed).
---
## Requirements
- **Python**: 3.x
- **Python dependencies**:
  - `psycopg2-binary`
  - (optional but recommended) `python-dotenv` (not required by this script)
If you already use the repo’s dependencies, this is covered by:
```bash
pip install -r requirements.txt
```
- **Postgres schema**: your database must have the tables defined in `db/schema-postgres.sql`, including:
  - `federal_register_documents.regulation_id_numbers` (note: **singular** `regulation_...`)
  - `cfrparts (frdocnum, title, cfrpart)` primary key
---
## Connection configuration
The script connects in this order:
1. **`DATABASE_URL`** if set (example: `postgres://user:pass@host:5432/dbname`)
2. Otherwise it uses individual environment variables:
   - **Preferred (app-style)**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
   - **Also supported (PG-style)**: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
### `.env` loading
The script attempts to load a `.env` automatically (using `os.environ.setdefault`, so it won’t override already-exported env vars):
- Prefers the **project root** `.env`
- Also checks a few parent directories and the current working directory
So in the common case, you can set DB credentials in the repo root `.env` and just run the script.
---
## Run
From the **project root**:
```bash
python3 db/ingest_federal_registry_document.py --json db/data/CMS_2026/federal_register/2025-21121.json
```
### Run with explicit connection env vars (recommended for prod)
```bash
DB_HOST=localhost DB_PORT=5432 DB_NAME=mirrulations DB_USER=YOUR_USER DB_PASSWORD='' \
python3 db/ingest_federal_registry_document.py --json db/data/CMS_2026/federal_register/2025-21121.json
```
Or using a single DSN:
```bash
DATABASE_URL="postgres://USER:PASSWORD@HOST:5432/mirrulations" \
python3 db/ingest_federal_registry_document.py --json db/data/CMS_2026/federal_register/2025-21121.json
```
---
## Input file expectations
The JSON file must be a single FR document object containing at minimum:
- `document_number` (string)
The script also reads (when present):
- `title`, `type`, `abstract`
- `publication_date`, `effective_on`
- `docket_ids` (array)
- `agencies` (array) → stores the **first** agency `id` as `agency_id` and all agency names as `agency_names`
- `topics` (array)
- `significant` (bool-ish)
- `regulation_id_numbers` (array)
- `html_url`, `pdf_url`, `json_url`
- `start_page`, `end_page`
- `cfr_references` (array of objects with `title` and `part`/`parts`) → becomes rows in `cfrparts`
---
## Troubleshooting
### `ValueError: invalid literal for int() with base 10: ''`
Cause: a port env var is set to an **empty string** (e.g. `DB_PORT=` or `PGPORT=`).
Fix:
- Set it to a number (usually `5432`), or remove it from the environment.
- The script is defensive and will fall back to `5432` when the variable is empty/invalid.
### `psycopg2.OperationalError: ... role "postgres" does not exist`
Cause: you’re falling back to default `PGUSER=postgres` but your Postgres install (common on macOS/Homebrew) does not have a `postgres` role.
Fix: set either:
- `DATABASE_URL`, or
- `DB_USER` / `PGUSER` to your actual Postgres role (often your macOS username).
### `UndefinedColumn: column "regulation_id_numbers" ... does not exist`
Cause: your database schema is older or has a mismatched column name (common typo: `regulations_id_numbers`).
Fix:
- Update your DB schema to match `db/schema-postgres.sql`, or
- Add/rename the column in `federal_register_documents` to **`regulation_id_numbers`**.
---
## Related docs / scripts
- `docs/setup_postgres.md` (initializing the local Postgres DB)
- `db/schema-postgres.sql` (authoritative schema)
- `docs/federal_register_usage.md` (FR data sources / usage)
