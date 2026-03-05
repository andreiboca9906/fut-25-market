#!/bin/bash
# Script to start Prometheus and Grafana monitoring without Docker

set -euo pipefail

echo "Starting FUT-26 Market Monitoring (no Docker)..."

PROMETHEUS_CONFIG="monitoring/prometheus.yml"
PROMETHEUS_DATA_DIR="monitoring/.prometheus-data"
GRAFANA_DATA_DIR="monitoring/.grafana-data"

mkdir -p "$PROMETHEUS_DATA_DIR" "$GRAFANA_DATA_DIR"

if ! command -v prometheus >/dev/null 2>&1; then
    echo "❌ prometheus binary not found. Install Prometheus and re-run."
    exit 1
fi

if ! command -v grafana-server >/dev/null 2>&1; then
    echo "❌ grafana-server binary not found. Install Grafana and re-run."
    exit 1
fi

# Stop stale local processes if they exist
pkill -f "prometheus --config.file=$PROMETHEUS_CONFIG" >/dev/null 2>&1 || true
pkill -f "grafana-server" >/dev/null 2>&1 || true

nohup prometheus \
  --config.file="$PROMETHEUS_CONFIG" \
  --storage.tsdb.path="$PROMETHEUS_DATA_DIR" \
  > monitoring/prometheus.log 2>&1 &

nohup grafana-server \
  --homepath /usr/share/grafana \
  --config /etc/grafana/grafana.ini \
  cfg:default.paths.data="$GRAFANA_DATA_DIR" \
  > monitoring/grafana.log 2>&1 &

echo ""
echo "Monitoring services started!"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000 (admin/admin by default)"
echo ""
echo "Logs: tail -f monitoring/prometheus.log monitoring/grafana.log"
