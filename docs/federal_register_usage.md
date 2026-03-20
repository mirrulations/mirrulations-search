# fr_to_postgres.py
### Federal Register → CFR → PostgreSQL Importer

Fetches CFR references from the Federal Register API and stores them in a local PostgreSQL database.

---

## Background: The Problem This Solves

Regulations.gov stores federal rulemaking dockets. Each docket document has a `cfrPart` field that is supposed to say which part of the Code of Federal Regulations (CFR) it relates to. However, a large number of documents have `null` in that field — the CFR data was never populated in the local record.

The Federal Register API is a separate system that often *does* have this CFR reference data. This script bridges that gap: given a regulations.gov docket ID and its corresponding Federal Register document number, it fetches the CFR references from the FR API and writes them into a structured PostgreSQL database so they can be queried and used downstream.

---

## The Text File

The text file is a report of these "gap" documents — regulations.gov dockets that have a null `cfrPart` locally but *do* have CFR data available via the Federal Register API. It is the primary input file for this script.

Each entry in text looks like this:

```
data/AMS/AMS-2005-0006/text-AMS-2005-0006/documents/AMS-2005-0006-0001.json | frDocNum=05-18758
  FR: Docket No. AO-388-A15 and AO-366-A44 | 7 CFR 1005
  FR: Docket No. AO-388-A15 and AO-366-A44 | 7 CFR 1007
  FR: DA-03-11 | 7 CFR 1005
  FR: DA-03-11 | 7 CFR 1007
```

Here is what each part means:

- **`data/AMS/AMS-2005-0006/...`** — the local file path to the regulations.gov document JSON on disk. The docket ID (`AMS-2005-0006`) is always the third path segment (index 2 when split on `/`).
- **`frDocNum=05-18758`** — the Federal Register document number that corresponds to this docket. This is what gets sent to the FR API.
- **`FR: Docket No. AO-388-A15 ... | 7 CFR 1005`** — a preview of the CFR references already known at report-generation time. These lines are informational only. The script ignores them and fetches CFR data fresh from the API instead, ensuring it always gets the most complete and structured response.

Some dockets reference multiple CFR parts (like `AMS-2005-0006` above with four `FR:` lines), while others reference just one. Each part becomes its own row in the database.

The text file covers AMS (Agricultural Marketing Service) dockets from 2005, all of which fall under Title 7 of the CFR (Agriculture). However, the script and database are not limited to any agency or title — they work with any valid FR document number.

---

## How to Create Your Own Text File

To create your own text file, you will need to list a path to the file, under that, you will just need to list the Federal Register Docket Number.
The docket number is used with the API to pull the CFR parts and fill in the missing columns. You can name the file anything, it just needs to be saved as a `.txt` file.

There is an example in /docs/, called dockets.txt, that can be used as a test or as a guide to how to create the text file.