# FR + eCFR Local Data Setup

## 1) Pull latest and install dependencies

```bash
git pull
pip install -r requirements.txt
```

## 2) Update your database

Fresh install:

```bash
./db/create_empty_db.sh
```

If `mirrulations` already exists:

```bash
psql -U <your_user> -d mirrulations -f db/migrations/001_fr_native_schema.sql
```

## 3) Download `documents.json`

Download from:
[documents.json.zip](https://drive.google.com/file/d/1htnOhjooaYgNRdobp1wj7et2e1UjlA7z/view?usp=sharing)

- File is several GB.
- Do not commit it to the repo.

## 4) Run the FR bulk loader

```bash
.venv/bin/python db/cfr_and_fr/load_fr_bulk.py /path/to/documents.json
```

- Typical runtime: about 20-40 minutes.
- Progress prints every 10,000 documents.

## 5) Run the eCFR links loader

```bash
.venv/bin/python db/cfr_and_fr/ecfr_to_links.py
```

- Usually under a minute.
- Populates `links(title, cfrPart, link)`.

## 6) Verify row counts

```bash
psql -U <your_user> -d mirrulations -c "SELECT
  (SELECT COUNT(*) FROM federal_register_documents) AS fr_docs,
  (SELECT COUNT(*) FROM federal_register_cfr_parts) AS cfr_parts,
  (SELECT COUNT(*) FROM links) AS links;"
```

Expected baseline:

- `fr_docs` around `994997`
- `cfr_parts` around `401407`
- `links` should be non-zero (exact count can vary over time)
