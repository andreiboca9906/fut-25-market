#!/bin/bash
# Start Celery worker with Prometheus multiprocess support

# Set up Prometheus multiprocess directory
export PROMETHEUS_MULTIPROC_DIR="/tmp/prometheus_multiproc"
mkdir -p $PROMETHEUS_MULTIPROC_DIR

# Clean up old metrics files on startup
rm -f $PROMETHEUS_MULTIPROC_DIR/*.db

# Load environment if script exists
if [ -f "./scripts/load-env.sh" ]; then
    source ./scripts/load-env.sh
fi

# Start Celery worker with all arguments passed through
exec uv run celery -A fut_market worker "$@"