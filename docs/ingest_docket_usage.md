# Using ingest_docket.py

## Overview

`ingest_docket.py` is a Python script that downloads docket bundles from the mirrulations S3 bucket and ingests regulatory data into PostgreSQL. It processes:

- **Docket metadata** (dockets table)
- **Regulatory documents** (documentsWithFRdoc table)
- **Public comments** (comments table)

The script fetches data from regulations.gov v4 API exports stored in S3 and loads them into your local PostgreSQL database.

## Quick Start

### 1. Download a Specific Docket

```bash
python db/ingest.py FAA-2025-0618
```

This downloads the docket and all its data (documents, comments, derived data) from S3 to `./FAA-2025-0618/`, then ingests it.

### 2. Use Local Docket Directory

If you already have docket data downloaded locally:

This ingests data from an existing local directory without downloading from S3.

## Usage Examples

### Workflow 1: Quick Test

```bash
# 1. Setup empty DB
./db/setup_postgres.sh 
./db/create_empty_db.sh

# 2. Run ingest
python db/ingest.py FAA-2025-0618 --user {your_username}

# 3. Testing
psql -d mirrulations -c "SELECT * FROM dockets LIMIT 10;"
psql -d mirrulations -c "SELECT * FROM comments LIMIT 10;"
psql -d mirrulations -c "SELECT * FROM comments LIMIT 10;"

```

### Workflow 2: Just Get Documents (Fast)

```bash
# Download and ingest documents only, no comments
python db/ingest_docket.py \
  --download-s3 FAA-2025-0618 \
  --skip-comments-download \
  --skip-comments-ingest
```

### Workflow 3: Update Existing Data

```bash
# Re-ingest a docket (upserts existing records)
python db/ingest_docket.py --download-s3 FAA-2025-0618
```

## Command-Line Options

### Ingest Options


### S3 Download Options


### After downloading from S3, the data is organized as:

```
<output-folder>/<DOCKET-ID>/
├── raw-data/
│   ├── docket/
│   │   └── *.json          # Docket metadata
│   ├── documents/
│   │   └── *.json          # Document metadata + FR references
│   ├── comments/
│   │   └── *.json          # Public comments (if downloaded)
│   └── binary-<DOCKET-ID>/ # Binary files (if --include-binary)
│       └── *.*
└── derived-data/           # Pre-computed data (if available)
    └── *.json
```
