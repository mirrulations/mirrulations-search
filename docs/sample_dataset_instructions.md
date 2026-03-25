# Sample Dataset Documentation — Mirrulations Search

## Overview

This document describes the sample dataset used for local development and testing of the Mirrulations Search application. The dataset consists of a single docket (`FAA-2025-0618`) with its associated documents and comments, providing a controlled and fully known set of data that can be used to verify search functionality, validate query results, and test ingestion pipelines.

This dataset is used in two ways:

- **PostgreSQL** — structured metadata for dockets, documents, and comments is stored via `db/sample-data.sql`, loaded by running `db/create_sample_db.sh`
- **OpenSearch** — comment text is indexed via `db/ingest_opensearch.py` for full-text search across three indices: `documents`, `comments`, and `comments_extracted_text`

For loading real fetched data beyond the sample, `db/ingest_comments.py` can download comment JSON directly from the public mirrulations S3 bucket and ingest them into PostgreSQL.

---

## Docket

There is one docket in the sample dataset.

| Field | Value |
|---|---|
| `docket_id` | `FAA-2025-0618` |
| `agency_id` | `FAA` |
| `docket_type` | `Rulemaking` |
| `rin` | `2120-AA64` |
| `docket_category` | `Pending` |
| `flex_subtype1` | `Airworthiness Directives` |
| `modify_date` | `2026-03-12T13:10:41Z` |
| `docket_title` | AD-2024-00637-T; The Boeing Company 767-200 Series; 767-300 Series; 767-300F Series; 767-400ER Series airplanes; Inspection of lower underwing longeron fitting |
| `docket_abstract` | Airworthiness Directives |

---

## Documents

There are five documents associated with docket `FAA-2025-0618`.

| `document_id` | `document_type` | `subtype` | `posted_date` | `title` |
|---|---|---|---|---|
| `FAA-2025-0618-0001` | Proposed Rule | Notice of Proposed Rulemaking (NPRM) | `2025-04-10` | Airworthiness Directives: The Boeing Company Airplanes |
| `FAA-2025-0618-0002` | Supporting & Related Material | Supplement | `2025-04-10` | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0009` | Public Submission | Comment(s) | `2025-10-03` | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0010` | Supporting & Related Material | Supplement | `2026-01-12` | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0011` | Rule | Final Rule | `2026-03-12` | Airworthiness Directives: The Boeing Company Airplanes |

**Notes:**
- `FAA-2025-0618-0001` is the original NPRM. `FAA-2025-0618-0011` is the final rule.
- `FAA-2025-0618-0001` and `FAA-2025-0618-0011` both reference `14 CFR Part 39` and have topics: `Air Transportation`, `Aircraft`, `Aviation Safety`, `Incorporation by Reference`, `Safety`.
- `FAA-2025-0618-0002` has inline comment text: `"Docket No. FAA-2025-0618; Project Identifier AD-2024-00637-T"`.
- `FAA-2025-0618-0009` has inline comment text: `"The Boeing Company: Docket No. FAA-2025-0618; Project Identifier AD-2024-00637-T."`.
- `FAA-2025-0618-0010` has inline comment text: `"Docket No. FAA-2025-0618; Project Identifier AD-2024-00637-T"`.

---

## Comments

There are six comments associated with docket `FAA-2025-0618`. All comments reference document `FAA-2025-0618-0001` (the NPRM).

| `comment_id` | `posted_date` | `submitter_org` | `comment_title` | Attachments |
|---|---|---|---|---|
| `FAA-2025-0618-0003` | `2025-04-11` | ProTech Aero Services Limited | Comment from ProTech Aero Services Limited | None |
| `FAA-2025-0618-0004` | `2025-04-24` | Aviation Partners Boeing | Comment from Aviation Partners Boeing | None |
| `FAA-2025-0618-0005` | `2025-05-09` | FedEx | Comment from FedEx | 1 PDF (`FedEx comment FAA-2025-0618`) |
| `FAA-2025-0618-0007` | `2025-05-27` | Boeing Commercial Airplane | Comment from Boeing Commercial Airplane | 1 PDF (`RA-25-01759`) |
| `FAA-2025-0618-0008` | `2025-05-28` | Delta Air Lines | Comment from Delta Air Lines | 3 PDFs (`Ref A_FAA-2025-0618`, `Ref C_AD 2012-15-12`, `NPRM FAA-2025-0618 Comment Letter`) |
| `FAA-2025-0618-0009` | `2025-10-03` | U.S. DOT/FAA | U.S. DOT/FAA - Supplemental AD Documents | 1 PDF (`Delta Airlines FAA-2025-0618 Comment Letter_Revised`) |

### Comment Details

**FAA-2025-0618-0003** — ProTech Aero Services Limited
Supports the FAA issuing the AD without change. No attachments.

**FAA-2025-0618-0004** — Aviation Partners Boeing
States that installation of winglets per STC ST01920SE does not affect compliance with the proposed actions. No attachments.

**FAA-2025-0618-0005** — FedEx
Comment text: "See attached file(s)". Substantive content in PDF attachment.

**FAA-2025-0618-0007** — Boeing Commercial Airplane
Comment text: "See attached file". Substantive content in PDF attachment titled "RA-25-01759".

**FAA-2025-0618-0008** — Delta Air Lines
Comment text: "See attached file(s)". Three PDF attachments: "Ref A_FAA-2025-0618", "Ref C_AD 2012-15-12", and "NPRM FAA-2025-0618 Comment Letter".

**FAA-2025-0618-0009** — U.S. DOT/FAA
Comment text: "The Boeing Company: Docket No. FAA-2025-0618; Project Identifier AD-2024-00637-T." One PDF attachment titled "Delta Airlines FAA-2025-0618 Comment Letter_Revised".

---

## OpenSearch Index Contents

The sample dataset populates three OpenSearch indices. The index names and their corresponding fields are defined in `src/mirrsearch/db.py`.

### `documents` index

Stores document metadata. Searched on the `title` and `comment` fields.

| `documentId` | `docketId` | `documentType` | `title` |
|---|---|---|---|
| `FAA-2025-0618-0001` | `FAA-2025-0618` | Proposed Rule | Airworthiness Directives: The Boeing Company Airplanes |
| `FAA-2025-0618-0002` | `FAA-2025-0618` | Supporting & Related Material | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0009` | `FAA-2025-0618` | Public Submission | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0010` | `FAA-2025-0618` | Supporting & Related Material | U.S. DOT/FAA - Supplemental AD Documents |
| `FAA-2025-0618-0011` | `FAA-2025-0618` | Rule | Airworthiness Directives: The Boeing Company Airplanes |

### `comments` index

Stores public comment text. Searched on the `commentText` field.

| `commentId` | `docketId` | `commentText` (summary) |
|---|---|---|
| `FAA-2025-0618-0003` | `FAA-2025-0618` | Supports the FAA issuing the AD without change |
| `FAA-2025-0618-0004` | `FAA-2025-0618` | Winglet installation per STC ST01920SE does not affect compliance with proposed actions |
| `FAA-2025-0618-0005` | `FAA-2025-0618` | See attached file(s) |
| `FAA-2025-0618-0007` | `FAA-2025-0618` | See attached file |
| `FAA-2025-0618-0008` | `FAA-2025-0618` | See attached file(s) |
| `FAA-2025-0618-0009` | `FAA-2025-0618` | The Boeing Company: Docket No. FAA-2025-0618; Project Identifier AD-2024-00637-T |

### `comments_extracted_text` index

Stores text extracted from PDF attachments on comments. Searched on the `extractedText` field. PDF extraction has been run on attachments from `FAA-2025-0618-0007`, `FAA-2025-0618-0008`, and `FAA-2025-0618-0009` as referenced in `db/ingest_opensearch.py`.

---

## Known Query Expectations

This section documents the expected search results for specific keywords against the sample dataset. Use these to verify that queries are working correctly after ingestion.

### Keywords expected to return results

| Search Term | Expected `document_match_count` | Expected `comment_match_count` | Notes |
|---|---|---|---|
| `Boeing` | 2 | 1 | Appears in two document titles and `commentText` of `FAA-2025-0618-0009` |
| `Airworthiness` | 2 | 0 | Appears in titles of `FAA-2025-0618-0001` and `FAA-2025-0618-0011` |
| `winglet` | 0 | 1 | Appears in `commentText` of `FAA-2025-0618-0004` |
| `AD-2024-00637-T` | 3 | 1 | Appears in inline comment fields of three documents and `commentText` of `FAA-2025-0618-0009` |
| `STC ST01920SE` | 0 | 1 | Phrase match in `commentText` of `FAA-2025-0618-0004` |
| `underwing longeron` | 0 | 0 | Present only in extracted PDF text — not in `commentText` or document titles |

### Keywords expected to return no results

| Search Term | Expected Result | Notes |
|---|---|---|
| `palliative` | 0 dockets | Not present anywhere in the dataset |
| `dialysis` | 0 dockets | Not present anywhere in the dataset |
| `marijuana` | 0 dockets | Not present anywhere in the dataset |
| `soccer` | 0 dockets | Not present anywhere in the dataset |

---

## Prerequisites

Before loading the sample dataset, make sure the following are set up on your machine.

**AWS CLI** — required by `ingest_comments.py` to download data from the public mirrulations S3 bucket.

Install the AWS CLI if you don't have it:
```bash
brew install awscli
```

Verify it is installed:
```bash
aws --version
```

You do not need AWS credentials for this — the mirrulations S3 bucket is public and uses unsigned access. However the AWS CLI itself must be present on your system or the download will fail.

---

## How to Load the Sample Dataset

### Step 1 — PostgreSQL: dockets and documents

Run the sample database setup script to create the schema and load docket and document metadata:

```bash
source .venv/bin/activate
./db/create_sample_db.sh
```

### Step 2 — PostgreSQL: comments

**Option A — From a locally downloaded docket folder:**

```bash
python db/ingest_comments.py --docket-dir ./FAA-2025-0618
```

**Option B — Download from S3 and ingest in one step:**

```bash
python db/ingest_comments.py --download-s3 FAA-2025-0618
```

**Option C — Download only, ingest later:**

```bash
python db/ingest_comments.py --download-s3 FAA-2025-0618 --download-only
```

**Dry run (validate without writing to DB):**

```bash
python db/ingest_comments.py --docket-dir ./FAA-2025-0618 --dry-run
```

### Step 3 — OpenSearch

Make sure OpenSearch is running, then ingest the sample data:

```bash
brew services start opensearch
python db/ingest_opensearch.py
```

Verify ingestion:

```bash
# Should return 5
curl -X GET "http://localhost:9200/documents/_count?pretty"

# Should return 6
curl -X GET "http://localhost:9200/comments/_count?pretty"
```

---

## Notes and Caveats

- **Foreign key ordering matters.** The docket row must exist in the `dockets` table before documents can be inserted, and document rows must exist before comments. `create_sample_db.sh` handles this order automatically. If running `ingest_comments.py` manually, ensure `create_sample_db.sh` has been run first.
- **`ingest_comments.py` handles missing FK references gracefully.** If a comment references a `document_id` or `docket_id` that does not exist in the database, the script will set that field to `NULL` rather than failing. A warning will be logged for each nulled reference.
- **`ingest_comments.py` supports upsert.** Running the script multiple times on the same data will not create duplicates — it updates existing records in place using `ON CONFLICT DO UPDATE`.
- **Most comment text is in PDF attachments.** Comments `FAA-2025-0618-0005`, `FAA-2025-0618-0007`, and `FAA-2025-0618-0008` contain only "See attached file(s)" as their inline comment text. Substantive content is in the PDF attachments, which are searchable only via the `comments_extracted_text` index after PDF extraction has been run.
- **`FAA-2025-0618-0009` appears as both a document and a comment.** It is recorded as a `Public Submission` document in the `documents` table and also as a comment in the `comments` table. This reflects how the regulations.gov API structures supplemental FAA submissions.
- **The `FAA-2025-0618/` folder should be gitignored.** Add it to `.gitignore` in `mirrulations-search` to prevent downloaded docket data from being committed to the repository.