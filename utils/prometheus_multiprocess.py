"""
Prometheus multiprocess support for Celery workers.
This allows metrics to be collected from multiple processes and aggregated.
"""

import os
import tempfile

from prometheus_client import CollectorRegistry, generate_latest, multiprocess

# Set up multiprocess directory
prometheus_multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
if not prometheus_multiproc_dir:
    # Create a temporary directory for development
    prometheus_multiproc_dir = tempfile.mkdtemp()
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = prometheus_multiproc_dir


def generate_metrics():
    """Generate aggregated metrics from all processes."""
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry)
