

from inference.core.managers.metrics import get_system_info
from coral_inference.core.env import (
    INFLUXDB_METRICS_BUCKET,
    INFLUXDB_METRICS_ORG,
    INFLUXDB_METRICS_TOKEN, 
    INFLUXDB_METRICS_URL
)


def patch_get_system_info():
    system_info = get_system_info()
    metrics = {
        'metrics_host': INFLUXDB_METRICS_URL,
        'metrics_token': INFLUXDB_METRICS_TOKEN,
        'metrics_org': INFLUXDB_METRICS_ORG,
        'metrics_bucket': INFLUXDB_METRICS_BUCKET
    }
    system_info.update(metrics)
    return system_info