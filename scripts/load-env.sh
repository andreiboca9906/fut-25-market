#!/bin/bash

# Load local environment variables
if [ -f .env.local ]; then
    export $(cat .env.local | xargs)
    echo "✓ Loaded environment variables from .env.local"
else
    echo "⚠ .env.local file not found, using default settings"
fi

# Execute the command passed as arguments
exec "$@"