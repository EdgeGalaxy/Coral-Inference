

from coral_inference.core.models.decorators import extend_method_after
from coral_inference.core.env import (
    INFLUXDB_METRICS_BUCKET,
    INFLUXDB_METRICS_ORG,
    INFLUXDB_METRICS_TOKEN, 
    INFLUXDB_METRICS_URL
)


@extend_method_after
def extend_system_info(result):
    metrics = {
        'metrics_host': INFLUXDB_METRICS_URL,
        'metrics_token': INFLUXDB_METRICS_TOKEN,
        'metrics_org': INFLUXDB_METRICS_ORG,
        'metrics_bucket': INFLUXDB_METRICS_BUCKET
    }
    result.update(metrics)
    return result