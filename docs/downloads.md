# Download System

## Overview
The download system allows users to request docket data as a ZIP file asynchronously via a Redis job queue. Jobs are tracked in Postgres and the resulting ZIPs are stored in S3.

## Environment Variables

Add the following to your `.env` file:

```dotenv
# S3 bucket where completed download ZIPs are stored
S3_BUCKET=

# Path to the mirrulations-fetch repo on your machine
FETCH_REPO_DIR=/path/to/mirrulations-fetch

# Path to the mirrulations-csv repo on your machine
CSV_REPO_DIR=/path/to/mirrulations-csv

# Redis connection (defaults shown)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

## How it works
1. User requests a download via `POST /download/request`
2. A job is created in Postgres and pushed to the Redis `download_queue`
3. The worker script picks up the job, runs mirrulations-fetch or mirrulations-csv, zips the output, and uploads to S3
4. User polls `GET /download/status/<job_id>` until ready, then hits `GET /download/<job_id>` to get the file