#!/bin/bash
# Script to start Prometheus and Grafana monitoring

echo "Starting FUT-25 Market Monitoring..."

# Check if docker network exists
if ! docker network inspect fut25_network >/dev/null 2>&1; then
    echo "Creating docker network: fut25_network"
    docker network create fut25_network
fi

# Start monitoring services
echo "Starting Prometheus and Grafana..."
docker-compose -f docker-compose.monitoring.yml up -d

echo ""
echo "Monitoring services started!"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:8040 (admin/admin)"
echo ""
echo "To view logs: docker-compose -f docker-compose.monitoring.yml logs -f"
echo "To stop: docker-compose -f docker-compose.monitoring.yml down"