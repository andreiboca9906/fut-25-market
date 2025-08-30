#!/bin/bash

# Load local environment variables
if [ -f .env ]; then
    export "$(xargs < .env)"
    echo "✓ Loaded environment variables from .env file"
else
    echo "⚠ .env file not found, using default settings"
fi
