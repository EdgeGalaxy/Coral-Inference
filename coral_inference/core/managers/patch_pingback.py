from coral_inference.core.env import (
    INFLUXDB_METRICS_BUCKET,
    INFLUXDB_METRICS_ORG, 
    INFLUXDB_METRICS_TOKEN, 
    INFLUXDB_METRICS_URL
)


def get_influxdb_metrics():
    return {
        'metrics_host': INFLUXDB_METRICS_URL,
        'metrics_token': INFLUXDB_METRICS_TOKEN,
        'metrics_org': INFLUXDB_METRICS_ORG,
        'metrics_bucket': INFLUXDB_METRICS_BUCKET
    }
