## Database Overview

### App ↔ OpenSearch on a secured node (e.g. EC2 + demo security)

If OpenSearch uses **HTTPS** and **basic auth** on port 9200 (typical after `install_demo_configuration.sh`), set in `.env`:

- `OPENSEARCH_USE_SSL=true` (optional if username + password are set — HTTPS is assumed)
- `OPENSEARCH_USER=admin`
- `OPENSEARCH_PASSWORD=…` (same value you used for `OPENSEARCH_INITIAL_ADMIN_PASSWORD` at install), **or** set `OPENSEARCH_INITIAL_ADMIN_PASSWORD` and the app will use it as the password.

Optional: `OPENSEARCH_VERIFY_CERTS=true` if you install a trusted CA (default is `false` for self-signed demo certs).

`curl` must use `https://localhost:9200` with `-k` and `-u admin:…`, not plain `http://`.

The Python client uses **HTTPS automatically when both username and password are set** and `OPENSEARCH_USE_SSL` is left unset (so older `.env` files without that flag still work). For rare **HTTP + basic auth**, set `OPENSEARCH_USE_SSL=false`.

**Ingest from a shell:** avoid `source .env` if the password contains `!` (bash history expansion). Either quote it in `.env` (`OPENSEARCH_PASSWORD='…!…'`) or run `python db/ingest_opensearch.py` alone — the script reloads `.env` from disk with override so values are not stuck on a bad shell export.

If `_search` returns **`index_not_found_exception`** for `documents` / `comments`, the cluster is reachable but **indices were never created** — run ingestion (e.g. `python db/ingest_opensearch.py` from the repo with the same `.env`), or restore from your production index snapshot.

#### Disk full → `index_create_block_exception` (403) on ingest

If ingest fails with **`cluster create-index blocked (api)`**, the volume is almost certainly **nearly full** (OpenSearch flood-stage / watermarks). Check `df -h /` and `_cat/allocation?v`.

**Fix (in order):**

1. **Free space or grow the EBS volume** — an **8 GiB** root disk is usually too small for Amazon Linux + PostgreSQL + OpenSearch + app + swap + logs. Prefer **≥20–30 GiB** for a dev all-in-one host.
2. After you have **hundreds of MB free at minimum**, clear the cluster block (HTTPS + auth):

   ```bash
   curl -sSk -u 'admin:YOUR_PASSWORD' -X PUT 'https://localhost:9200/_cluster/settings' \
     -H 'Content-Type: application/json' \
     -d '{"persistent":{"cluster.blocks.create_index":null}}'
   ```

3. Re-run **`python db/ingest_opensearch.py`**.

`PUT _all/_settings` to clear `read_only_allow_delete` may return **403** for the demo `admin` user (security plugin); that call is mainly for existing indices. With **no app indices yet**, fixing **disk +** `cluster.blocks.create_index` is usually enough.

**Quick cleanups on a tight disk (run with care):** `sudo journalctl --vacuum-time=3d`, `sudo dnf clean all`, remove old logs under `/var/log`, and avoid duplicate **swapfiles** if the deploy script ran multiple times.

---

Search aggregations use OpenSearch `terms` buckets, which **require an explicit `size`** (there is no unbounded “return all” mode). Defaults in code aim for typical cluster limits (e.g. `max_terms_count` ~65535 for comment IDs per docket). Tune for very large dockets with:

- `OPENSEARCH_COMMENT_ID_TERMS_SIZE` — distinct `commentId` buckets per docket (must align with cluster/index `max_terms_count` if raised).
- `OPENSEARCH_MATCH_DOCKET_BUCKET_SIZE` — how many docket buckets to return for corpus-wide text match queries (trade memory/latency vs completeness).

If a single docket can exceed those limits, counts may be approximate unless you move to a **composite aggregation** (paged) or a different counting strategy.

There are three OpenSearch indices:

- `comments`
- `comments_extracted_text`
- `documents`

---

## `comments` Index

```json
{
  "comments": {
    "mappings": {
      "properties": {
        "commentId": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "commentText": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        },
        "docketId": {
          "type": "text",
          "fields": {
            "keyword": {
              "type": "keyword",
              "ignore_above": 256
            }
          }
        }
      }
    }
  }
}
```
Has around 25 million json files

## `comments_extracted_text`
```json
{
  "comments_extracted_text" : {
    "mappings" : {
      "properties" : {
        "attachmentId" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "commentId" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "docketId" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "extractedMethod" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "extractedText" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        }
      }
    }
  }
}
```
Has around 2.5 million json files with text extracted from PDF attachments on comments. Connects to comments via commentId and docketId

## `documents_text`
```json
{
  "documents_text" : {
    "mappings" : {
      "properties" : {
        "docketId" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "documentId" : {
          "type" : "text",
          "fields" : {
            "keyword" : {
              "type" : "keyword",
              "ignore_above" : 256
            }
          }
        },
        "documentText" : {
          "type" : "text"
        }
      }
    }
  }
}
```
Around 2 million documents that can connect with documentId and docketId
