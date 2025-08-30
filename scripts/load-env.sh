#!/bin/bash

# Load local environment variables
if [ -f .env ]; then
    # Source the .env file, which handles comments and complex values properly
    set -a
    source .env
    set +a
    echo "✓ Loaded environment variables from .env file"
else
    echo "⚠ .env file not found, using default settings"
fi
