# Federal Register Bulk Load (FR-native Postgres schema)

The bulk loader in `db/cfr_and_fr/load_fr_bulk.py` expects a large `documents.json` file that is **not** stored in this repo. You provide it locally (for example by unzipping the archive you download).

## If setting up fresh

1. Create an empty database + load the current schema:
   ```bash
   ./db/create_empty_db.sh
   ```

## If the DB is already running

1. Re-apply the FR-native migration SQL to the existing `mirrulations` database:
   ```bash
   psql -U <user> -d mirrulations -f db/migrations/001_fr_native_schema.sql
   ```

## Load `documents.json`

1. Point the loader at your local copy of `documents.json`:
   ```bash
   bash.venv/bin/python db/cfr_and_fr/load_fr_bulk.py /path/to/their/documents.json
   ```

Notes:
- The loader accepts the JSON file path as a CLI argument, so it works with zipped/external datasets as long as you extract `documents.json` somewhere locally.
- `documents.json` can be very large; keep it outside the git repo.

