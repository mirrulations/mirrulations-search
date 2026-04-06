# Regulations.gov HTML Backfill

Two scripts that work together to identify dockets missing `.html` files and download them from the regulations.gov API.

---

## Overview

The workflow is two steps:

1. **`count_docket_files.py`** — Scans your local `data/` folder and produces a report identifying which dockets have `.htm` files and which don't.
2. **`regulations_backfill.py`** — Reads that report, targets only the dockets missing `.htm` files, queries the regulations.gov API for each one, and downloads any `.html` files it finds.

---

## Folder Structure

Your project folder should look like this:

```
your-folder/
  count_docket_files.py
  regulations_backfill.py
  .env
  requirements.txt
  data/
    AGENCY/
      AGENCY-DOCKETID/
        text-AGENCY-DOCKETID/
          documents/
            *.htm, *.pdf, etc.
```

After running the scripts, these files will be created automatically:

```
  docket_file_counts.txt     ← full file type breakdown per docket
  docket_htm_status.txt      ← which dockets have/don't have .htm files
  output/                    ← downloaded .html files land here
  checkpoint.json            ← tracks progress so you can resume
  stats.json                 ← running download stats
  failed.csv                 ← any dockets/documents that errored
```

---

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Create a `.env` file** in the same folder as the scripts:

```
REGULATIONS_API_KEY=your_key_here
```

Get a free API key at [api.data.gov/signup](https://api.data.gov/signup/).

---

## Step 1 — Scan Your Local Data (`count_docket_files.py`)

Walks the `data/` folder and produces two report files.

```bash
python count_docket_files.py
```

**Output files:**

- `docket_file_counts.txt` — Full breakdown of every file type (`.pdf`, `.htm`, `.json`, etc.) for every docket across every agency.
- `docket_htm_status.txt` — Focused report showing which dockets have `.htm` files (`[YES]`) and which don't (`[NO ]`). This file is the input to Step 2.

**Example output in `docket_htm_status.txt`:**
```
  Contains HTM files (2):
    [YES]  WAPA-2005-0001  (1 .htm file(s))
    [YES]  WAPA-2005-0002  (1 .htm file(s))

  No HTM files (3):
    [NO ]  WAPA-2025-0001
    [NO ]  WAPA-2025-0002
    [NO ]  WAPA-2026-0001
```

---

## Step 2 — Download Missing HTML Files (`regulations_backfill.py`)

Reads `docket_htm_status.txt`, finds every `[NO ]` docket, and queries the regulations.gov API to download any `.html` files available for those dockets.

**Basic usage:**
```bash
python regulations_backfill.py
```

**Specify a different input file:**
```bash
python regulations_backfill.py --input path/to/docket_htm_status.txt
```

**Test without downloading anything (recommended first run):**
```bash
python regulations_backfill.py --dry-run
```

**Retry any previously failed dockets:**
```bash
python regulations_backfill.py --retry
```

**Downloaded files are saved to:**
```
./output/{agency}/{docket}/text-{docket}/documents/{filename}.html
```

---

## Resuming After a Stop

You can stop the script at any time with `Ctrl+C`. Progress is saved to `checkpoint.json` after every completed docket. Re-running the script will skip everything already completed and pick up where it left off.

---

## Monitoring Progress

Every 100 dockets the script prints a summary:

```
──────────────────────────────────────────────────────
  Elapsed           :  01h 23m 45s
  Dockets processed :     5,200 / 158,616 (3.3%)
  Documents scanned :    18,400
  Already local     :       240  (skipped)
  No .html in API   :    15,300
  .html downloaded  :     2,860
  Failures          :         3
──────────────────────────────────────────────────────
```

A snapshot is also saved to `stats.json` after every docket so you can check it at any time without waiting for the next printed summary.

---

## Handling Failures

Any docket or document that fails (API error, download error) is logged to `failed.csv` with the reason. The script continues past failures rather than stopping. Once the main run finishes, retry all failures in one pass:

```bash
python regulations_backfill.py --retry
```

---

## API Rate Limits

The regulations.gov API allows **1,000 requests per hour**. The script runs at ~970 requests/hour by default (3.7 second delay between calls), staying safely under the cap. If you hit a rate limit anyway, the script will automatically back off and wait before retrying.

For large runs across all 158,000+ dockets, the process will take several weeks at this rate. You can request a higher rate limit from [api.data.gov](https://api.data.gov/) for bulk/research use cases.

---

## requirements.txt

```
requests
python-dotenv
```
