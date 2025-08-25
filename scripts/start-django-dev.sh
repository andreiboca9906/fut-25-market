#!/bin/bash
# Start Django development server with Prometheus multiprocess support

# Set up Prometheus multiprocess directory
export PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_multiproc"
mkdir -p $PROMETHEUS_MULTIPROC_DIR

# Load environment if script exists
if [ -f "./scripts/load-env.sh" ]; then
    source ./scripts/load-env.sh
fi

# Start Django development server
exec uv run python manage.py runserver 8010