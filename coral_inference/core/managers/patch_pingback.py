from coral_inference.core.env import (
    INFLUXDB_METRICS_DATABASE,
    INFLUXDB_METRICS_TOKEN,
    INFLUXDB_METRICS_URL,
)
from coral_inference.core.models.utils import get_runtime_platform


def get_influxdb_metrics():
    return {
        "metrics_host": INFLUXDB_METRICS_URL,
        "metrics_token": INFLUXDB_METRICS_TOKEN,
        "metrics_database": INFLUXDB_METRICS_DATABASE,
        "run_env": get_runtime_platform(),
    }
