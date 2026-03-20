# Federal Register bulk load (FR-native schema)

Download the dataset: [`documents.json.zip`](https://drive.google.com/file/d/1htnOhjooaYgNRdobp1wj7et2e1UjlA7z/view?usp=sharing)

1) Create the DB (empty + schema)
```bash
./db/create_empty_db.sh
```

If the DB already exists:
```bash
psql -U <user> -d mirrulations -f db/migrations/001_fr_native_schema.sql
```

2) Unzip to get `documents.json`
```bash
unzip documents.json.zip -d /path/to/extracted
```

3) Run the loader (points to your local `documents.json`)
```bash
.venv/bin/python db/cfr_and_fr/load_fr_bulk.py /path/to/extracted/documents.json
```

The loader expects `documents.json` to be a top-level JSON array. Items without `document_number` are skipped; items should include `docket_ids` and `cfr_references` to populate the CFR parts table.

