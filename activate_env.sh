#!/bin/bash

echo "Loading environment from .env..."

if [ ! -f .env ]; then
    echo "Error: .env file not found. Create one in the project root."
    echo "See .env.example for the required variables."
    return 1
fi

set -a
source .env
set +a

echo "Environment ready!"
