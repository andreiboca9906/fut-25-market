import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fut_market.settings")
app = Celery("fut_market")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Explicitly include metrics_tasks
app.autodiscover_tasks(["players"], related_name="metrics_tasks")
