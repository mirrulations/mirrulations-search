#!/bin/bash
# Ingest script for fetching and ingesting docket data

# Validate docket_id is provided
if [[ -z "$1" ]]; then
    echo "Error: docket_id argument is required"
    echo "Usage: $0 <docket_id>"
    exit 1
fi

# Call the Python ingest script
python3 "$(dirname "$0")/ingest.py" "$1" --user "$(whoami)"
